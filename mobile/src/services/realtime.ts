import { z } from "zod";

import { API_BASE_URL } from "./api";
import { RealtimeEvent, realtimeEventSchema } from "../types/realtime";

export type RealtimeConnectionState =
  "connecting" | "connected" | "reconnecting" | "disconnected" | "error";

export type RealtimeCloseDetails = {
  code: number;
  reason: string;
};

type RealtimeMessage = {
  data: unknown;
};

export interface RealtimeSocket {
  onopen: (() => void) | null;
  onmessage: ((message: RealtimeMessage) => void) | null;
  onerror: (() => void) | null;
  onclose: ((details: RealtimeCloseDetails) => void) | null;
  close(code?: number, reason?: string): void;
}

export type RealtimeSocketOptions = {
  headers: Record<string, string>;
};

export type RealtimeSocketFactory = (
  url: string,
  options: RealtimeSocketOptions,
) => RealtimeSocket;

type NativeWebSocketConstructor = new (
  url: string,
  protocols?: string | string[],
  options?: RealtimeSocketOptions,
) => RealtimeSocket;

export type HouseholdRealtimeClientOptions = {
  householdId: string;
  accessToken: string;
  onEvent: (event: RealtimeEvent) => void;
  onStateChange?: (state: RealtimeConnectionState) => void;
  onInvalidMessage?: (data: unknown) => void;
  onClose?: (details: RealtimeCloseDetails) => void;
  onReconnect?: () => void;
  apiUrl?: string;
  socketFactory?: RealtimeSocketFactory;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
};

const householdIdSchema = z.uuid();
const NON_RETRYABLE_CLOSE_CODES = new Set([1000, 4401, 4404]);
const DEFAULT_RECONNECT_INITIAL_DELAY_MS = 1_000;
const DEFAULT_RECONNECT_MAX_DELAY_MS = 30_000;

export function buildHouseholdRealtimeUrl(
  householdId: string,
  apiUrl: string = API_BASE_URL,
): string {
  householdIdSchema.parse(householdId);
  const url = new URL(`/api/v1/households/${householdId}/ws`, apiUrl);

  if (url.protocol === "http:") {
    url.protocol = "ws:";
  } else if (url.protocol === "https:") {
    url.protocol = "wss:";
  } else {
    throw new Error("The API URL must use HTTP or HTTPS.");
  }

  return url.toString();
}

export function parseRealtimeEvent(data: unknown): RealtimeEvent | null {
  if (typeof data !== "string") {
    return null;
  }

  try {
    const result = realtimeEventSchema.safeParse(JSON.parse(data));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

function createNativeSocket(
  url: string,
  options: RealtimeSocketOptions,
): RealtimeSocket {
  const Socket = WebSocket as unknown as NativeWebSocketConstructor;
  return new Socket(url, undefined, options);
}

export class HouseholdRealtimeClient {
  private readonly householdId: string;
  private readonly accessToken: string;
  private readonly onEvent: (event: RealtimeEvent) => void;
  private readonly onStateChange?: (state: RealtimeConnectionState) => void;
  private readonly onInvalidMessage?: (data: unknown) => void;
  private readonly onClose?: (details: RealtimeCloseDetails) => void;
  private readonly onReconnect?: () => void;
  private readonly url: string;
  private readonly socketFactory: RealtimeSocketFactory;
  private readonly reconnectInitialDelayMs: number;
  private readonly reconnectMaxDelayMs: number;
  private socket: RealtimeSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private reconnectEnabled = false;
  private hasConnected = false;
  private state: RealtimeConnectionState = "disconnected";

  constructor(options: HouseholdRealtimeClientOptions) {
    if (!options.accessToken.trim()) {
      throw new Error("An access token is required for real-time connections.");
    }

    this.householdId = householdIdSchema.parse(options.householdId);
    this.accessToken = options.accessToken;
    this.onEvent = options.onEvent;
    this.onStateChange = options.onStateChange;
    this.onInvalidMessage = options.onInvalidMessage;
    this.onClose = options.onClose;
    this.onReconnect = options.onReconnect;
    this.url = buildHouseholdRealtimeUrl(
      this.householdId,
      options.apiUrl ?? API_BASE_URL,
    );
    this.socketFactory = options.socketFactory ?? createNativeSocket;
    this.reconnectInitialDelayMs =
      options.reconnectInitialDelayMs ?? DEFAULT_RECONNECT_INITIAL_DELAY_MS;
    this.reconnectMaxDelayMs =
      options.reconnectMaxDelayMs ?? DEFAULT_RECONNECT_MAX_DELAY_MS;

    if (
      !Number.isFinite(this.reconnectInitialDelayMs) ||
      !Number.isFinite(this.reconnectMaxDelayMs) ||
      this.reconnectInitialDelayMs <= 0 ||
      this.reconnectMaxDelayMs < this.reconnectInitialDelayMs
    ) {
      throw new Error(
        "Reconnect delays must be positive and the maximum must not be smaller than the initial delay.",
      );
    }
  }

  get connectionState(): RealtimeConnectionState {
    return this.state;
  }

  connect(): void {
    this.reconnectEnabled = true;
    if (this.socket !== null || this.reconnectTimer !== null) {
      return;
    }

    this.openSocket(false);
  }

  disconnect(): void {
    this.reconnectEnabled = false;
    this.reconnectAttempt = 0;
    this.hasConnected = false;
    this.cancelReconnect();
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close(1000, "Client disconnected.");
    }
    this.setState("disconnected");
  }

  private openSocket(isReconnect: boolean): void {
    if (!this.reconnectEnabled || this.socket !== null) {
      return;
    }

    this.setState(isReconnect ? "reconnecting" : "connecting");
    let socket: RealtimeSocket;
    try {
      socket = this.socketFactory(this.url, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });
    } catch {
      this.setState("error");
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;
    socket.onopen = () => {
      if (this.socket === socket) {
        const recovered = this.hasConnected;
        this.hasConnected = true;
        this.reconnectAttempt = 0;
        this.setState("connected");
        if (recovered) {
          this.onReconnect?.();
        }
      }
    };
    socket.onmessage = ({ data }) => {
      if (this.socket !== socket) {
        return;
      }

      const event = parseRealtimeEvent(data);
      if (event === null || event.household_id !== this.householdId) {
        this.onInvalidMessage?.(data);
        return;
      }
      this.onEvent(event);
    };
    socket.onerror = () => {
      if (this.socket === socket) {
        this.setState("error");
      }
    };
    socket.onclose = (details) => {
      if (this.socket !== socket) {
        return;
      }
      this.socket = null;
      this.onClose?.(details);
      if (this.reconnectEnabled && !NON_RETRYABLE_CLOSE_CODES.has(details.code)) {
        this.scheduleReconnect();
      } else {
        this.reconnectEnabled = false;
        this.hasConnected = false;
        this.setState("disconnected");
      }
    };
  }

  private scheduleReconnect(): void {
    if (!this.reconnectEnabled || this.reconnectTimer !== null) {
      return;
    }

    this.reconnectAttempt += 1;
    const delay = Math.min(
      this.reconnectInitialDelayMs * 2 ** Math.min(this.reconnectAttempt - 1, 30),
      this.reconnectMaxDelayMs,
    );
    this.setState("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket(true);
    }, delay);
  }

  private cancelReconnect(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setState(state: RealtimeConnectionState): void {
    if (this.state === state) {
      return;
    }
    this.state = state;
    this.onStateChange?.(state);
  }
}
