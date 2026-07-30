import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { AppState, AppStateStatus } from "react-native";

import {
  refreshHouseholdGroceryQueries,
  refreshShoppingSessionGroceryQueries,
  synchronizeGroceryRealtimeEvent,
} from "../features/grocery/realtimeSynchronization";
import {
  HouseholdRealtimeClient,
  HouseholdRealtimeClientOptions,
  RealtimeConnectionState,
} from "../services/realtime";
import { RealtimeEventOrderingTracker } from "../services/realtimeEventOrdering";

export interface HouseholdRealtimeConnection {
  connect(): void;
  disconnect(): void;
}

export type HouseholdRealtimeClientFactory = (
  options: HouseholdRealtimeClientOptions,
) => HouseholdRealtimeConnection;

export interface RealtimeAppState {
  currentState: AppStateStatus;
  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void };
}

export type UseHouseholdRealtimeOptions = {
  householdId: string | null;
  accessToken: string | null;
  onError?: (error: unknown) => void;
  clientFactory?: HouseholdRealtimeClientFactory;
  appState?: RealtimeAppState;
};

const createHouseholdRealtimeClient: HouseholdRealtimeClientFactory = (options) =>
  new HouseholdRealtimeClient(options);
const mobileAppState: RealtimeAppState = AppState;

export function useHouseholdRealtime({
  householdId,
  accessToken,
  onError,
  clientFactory = createHouseholdRealtimeClient,
  appState = mobileAppState,
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
    let appIsActive = appState.currentState === "active";
    const eventOrdering = new RealtimeEventOrderingTracker();
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
          if (active && appIsActive) {
            setConnectionState(state);
          }
        },
        onEvent: (event) => {
          if (!active || !appIsActive) {
            return;
          }

          const decision = eventOrdering.evaluate(event);
          if (decision.status === "accepted") {
            reportFailure(synchronizeGroceryRealtimeEvent(queryClient, event));
          } else if (decision.status === "gap") {
            reportFailure(
              refreshShoppingSessionGroceryQueries(
                queryClient,
                event.household_id,
                event.payload.shopping_session_id,
              ),
            );
          }
        },
        onReconnect: () => {
          if (active && appIsActive) {
            eventOrdering.reset();
            reportFailure(refreshHouseholdGroceryQueries(queryClient, householdId));
          }
        },
      });
    } catch (error) {
      setConnectionState("error");
      errorHandlerRef.current?.(error);
      return;
    }

    const appStateSubscription = appState.addEventListener("change", (nextState) => {
      const nextIsActive = nextState === "active";
      if (!active || nextIsActive === appIsActive) {
        return;
      }

      appIsActive = nextIsActive;
      if (appIsActive) {
        eventOrdering.reset();
        reportFailure(refreshHouseholdGroceryQueries(queryClient, householdId));
        client.connect();
      } else {
        client.disconnect();
        setConnectionState("disconnected");
      }
    });

    if (appIsActive) {
      client.connect();
    } else {
      setConnectionState("disconnected");
    }
    return () => {
      active = false;
      appStateSubscription.remove();
      client.disconnect();
    };
  }, [accessToken, appState, clientFactory, householdId, queryClient]);

  return connectionState;
}
