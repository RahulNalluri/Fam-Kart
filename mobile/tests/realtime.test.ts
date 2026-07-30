import {
  HouseholdRealtimeClient,
  RealtimeCloseDetails,
  RealtimeConnectionState,
  RealtimeSocket,
  RealtimeSocketFactory,
  buildHouseholdRealtimeUrl,
  parseRealtimeEvent,
} from "../src/services/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";
const itemId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const userId = "44444444-4444-4444-8444-444444444444";
const eventId = "55555555-5555-4555-8555-555555555555";

function buildEvent(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    event_id: eventId,
    event_type: "grocery.item_added",
    household_id: householdId,
    occurred_at: "2026-07-30T12:00:00Z",
    payload: {
      shopping_session_id: sessionId,
      grocery_item_id: itemId,
      actor_user_id: userId,
      item_name: "Milk",
      sequence_number: 1,
    },
    ...overrides,
  };
}

class FakeSocket implements RealtimeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((details: RealtimeCloseDetails) => void) | null = null;
  close = jest.fn<void, [number?, string?]>();
}

function buildClient() {
  const socket = new FakeSocket();
  const socketFactory = jest.fn<
    ReturnType<RealtimeSocketFactory>,
    Parameters<RealtimeSocketFactory>
  >(() => socket);
  const onEvent = jest.fn();
  const onInvalidMessage = jest.fn();
  const onStateChange = jest.fn<void, [RealtimeConnectionState]>();
  const onClose = jest.fn<void, [RealtimeCloseDetails]>();
  const client = new HouseholdRealtimeClient({
    householdId,
    accessToken: "access-token",
    apiUrl: "http://192.168.0.10:8000",
    socketFactory,
    onEvent,
    onInvalidMessage,
    onStateChange,
    onClose,
  });

  return {
    client,
    socket,
    socketFactory,
    onEvent,
    onInvalidMessage,
    onStateChange,
    onClose,
  };
}

describe("mobile household real-time client", () => {
  it("builds ws and wss URLs from HTTP API URLs", () => {
    expect(buildHouseholdRealtimeUrl(householdId, "http://localhost:8000")).toBe(
      `ws://localhost:8000/api/v1/households/${householdId}/ws`,
    );
    expect(
      buildHouseholdRealtimeUrl(householdId, "https://api.familykart.example"),
    ).toBe(`wss://api.familykart.example/api/v1/households/${householdId}/ws`);
  });

  it("connects with the access token in the Authorization header", () => {
    const { client, socket, socketFactory, onStateChange } = buildClient();

    client.connect();
    client.connect();

    expect(socketFactory).toHaveBeenCalledTimes(1);
    expect(socketFactory).toHaveBeenCalledWith(
      `ws://192.168.0.10:8000/api/v1/households/${householdId}/ws`,
      { headers: { Authorization: "Bearer access-token" } },
    );
    expect(client.connectionState).toBe("connecting");

    socket.onopen?.();

    expect(client.connectionState).toBe("connected");
    expect(onStateChange.mock.calls).toEqual([["connecting"], ["connected"]]);
  });

  it("validates and delivers a household grocery event", () => {
    const { client, socket, onEvent, onInvalidMessage } = buildClient();
    const event = buildEvent();

    client.connect();
    socket.onmessage?.({ data: JSON.stringify(event) });

    expect(onEvent).toHaveBeenCalledWith(event);
    expect(onInvalidMessage).not.toHaveBeenCalled();
    expect(parseRealtimeEvent(JSON.stringify(event))).toEqual(event);
  });

  it("rejects malformed and cross-household messages", () => {
    const { client, socket, onEvent, onInvalidMessage } = buildClient();
    const malformed = "not-json";
    const otherHousehold = JSON.stringify(
      buildEvent({ household_id: "66666666-6666-4666-8666-666666666666" }),
    );

    client.connect();
    socket.onmessage?.({ data: malformed });
    socket.onmessage?.({ data: otherHousehold });

    expect(onEvent).not.toHaveBeenCalled();
    expect(onInvalidMessage.mock.calls).toEqual([[malformed], [otherHousehold]]);
  });

  it("reports socket errors and server close details", () => {
    const { client, socket, onStateChange, onClose } = buildClient();

    client.connect();
    socket.onerror?.();

    expect(client.connectionState).toBe("error");

    socket.onclose?.({ code: 4401, reason: "Authentication required." });

    expect(client.connectionState).toBe("disconnected");
    expect(onStateChange.mock.calls).toEqual([
      ["connecting"],
      ["error"],
      ["disconnected"],
    ]);
    expect(onClose).toHaveBeenCalledWith({
      code: 4401,
      reason: "Authentication required.",
    });
  });

  it("closes locally and detaches all socket handlers", () => {
    const { client, socket, onEvent } = buildClient();

    client.connect();
    client.disconnect();

    expect(socket.close).toHaveBeenCalledWith(1000, "Client disconnected.");
    expect(socket.onopen).toBeNull();
    expect(socket.onmessage).toBeNull();
    expect(socket.onerror).toBeNull();
    expect(socket.onclose).toBeNull();
    expect(client.connectionState).toBe("disconnected");
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("reports a synchronous socket creation failure", () => {
    const onStateChange = jest.fn<void, [RealtimeConnectionState]>();
    const client = new HouseholdRealtimeClient({
      householdId,
      accessToken: "access-token",
      onEvent: jest.fn(),
      onStateChange,
      socketFactory: () => {
        throw new Error("socket unavailable");
      },
    });

    client.connect();

    expect(client.connectionState).toBe("error");
    expect(onStateChange.mock.calls).toEqual([["connecting"], ["error"]]);
  });
});
