import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  refreshHouseholdGroceryQueries,
  synchronizeGroceryRealtimeEvent,
} from "../features/grocery/realtimeSynchronization";
import {
  HouseholdRealtimeClient,
  HouseholdRealtimeClientOptions,
  RealtimeConnectionState,
} from "../services/realtime";

export interface HouseholdRealtimeConnection {
  connect(): void;
  disconnect(): void;
}

export type HouseholdRealtimeClientFactory = (
  options: HouseholdRealtimeClientOptions,
) => HouseholdRealtimeConnection;

export type UseHouseholdRealtimeOptions = {
  householdId: string | null;
  accessToken: string | null;
  onError?: (error: unknown) => void;
  clientFactory?: HouseholdRealtimeClientFactory;
};

const createHouseholdRealtimeClient: HouseholdRealtimeClientFactory = (options) =>
  new HouseholdRealtimeClient(options);

export function useHouseholdRealtime({
  householdId,
  accessToken,
  onError,
  clientFactory = createHouseholdRealtimeClient,
}: UseHouseholdRealtimeOptions): RealtimeConnectionState {
  const queryClient = useQueryClient();
  const errorHandlerRef = useRef(onError);
  const [connectionState, setConnectionState] =
    useState<RealtimeConnectionState>("disconnected");
  errorHandlerRef.current = onError;

  useEffect(() => {
    if (!householdId || !accessToken?.trim()) {
      setConnectionState("disconnected");
      return;
    }

    let active = true;
    const reportFailure = (operation: Promise<void>) => {
      void operation.catch((error: unknown) => {
        if (active) {
          errorHandlerRef.current?.(error);
        }
      });
    };

    let client: HouseholdRealtimeConnection;
    try {
      client = clientFactory({
        householdId,
        accessToken,
        onStateChange: (state) => {
          if (active) {
            setConnectionState(state);
          }
        },
        onEvent: (event) => {
          if (active) {
            reportFailure(synchronizeGroceryRealtimeEvent(queryClient, event));
          }
        },
        onReconnect: () => {
          if (active) {
            reportFailure(refreshHouseholdGroceryQueries(queryClient, householdId));
          }
        },
      });
    } catch (error) {
      setConnectionState("error");
      errorHandlerRef.current?.(error);
      return;
    }

    client.connect();
    return () => {
      active = false;
      client.disconnect();
    };
  }, [accessToken, clientFactory, householdId, queryClient]);

  return connectionState;
}
