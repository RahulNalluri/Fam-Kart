import { useEffect, useRef, useState } from "react";
import { AppState, AppStateStatus } from "react-native";

import {
  SyncCoordinatorSnapshot,
  SyncCoordinatorStatus,
} from "../features/offline/syncCoordinator";

export interface SyncLifecycleAppState {
  currentState: AppStateStatus;
  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void };
}

export interface SyncLifecycleCoordinator {
  getSnapshot(): SyncCoordinatorSnapshot;
  subscribe(listener: (snapshot: SyncCoordinatorSnapshot) => void): () => void;
  start(): Promise<void>;
  stop(): void;
}

export type HouseholdSyncCoordinatorFactory = (
  householdId: string,
) => SyncLifecycleCoordinator;

export type UseHouseholdSyncLifecycleOptions = Readonly<{
  householdId: string | null;
  coordinatorFactory: HouseholdSyncCoordinatorFactory;
  appState?: SyncLifecycleAppState;
  onError?: (error: unknown) => void;
}>;

const STOPPED_SNAPSHOT: SyncCoordinatorSnapshot = Object.freeze({
  connectivity: "unknown",
  status: "stopped",
  lastProcessedCount: 0,
});

function errorSnapshot(status: SyncCoordinatorStatus): SyncCoordinatorSnapshot {
  return {
    connectivity: "unknown",
    status,
    lastProcessedCount: 0,
  };
}

const mobileAppState: SyncLifecycleAppState = AppState;

export function useHouseholdSyncLifecycle({
  householdId,
  coordinatorFactory,
  appState = mobileAppState,
  onError,
}: UseHouseholdSyncLifecycleOptions): SyncCoordinatorSnapshot {
  const [snapshot, setSnapshot] = useState<SyncCoordinatorSnapshot>(STOPPED_SNAPSHOT);
  const errorHandlerRef = useRef(onError);
  errorHandlerRef.current = onError;

  useEffect(() => {
    if (!householdId?.trim()) {
      setSnapshot(STOPPED_SNAPSHOT);
      return;
    }

    let mounted = true;
    let appIsActive = appState.currentState === "active";
    let coordinator: SyncLifecycleCoordinator;

    try {
      coordinator = coordinatorFactory(householdId);
    } catch (error) {
      setSnapshot(errorSnapshot("error"));
      errorHandlerRef.current?.(error);
      return;
    }

    setSnapshot(coordinator.getSnapshot());
    const unsubscribeCoordinator = coordinator.subscribe((nextSnapshot) => {
      if (mounted) {
        setSnapshot(nextSnapshot);
      }
    });

    const startCoordinator = () => {
      void coordinator.start().catch((error: unknown) => {
        if (mounted && appIsActive) {
          setSnapshot(errorSnapshot("error"));
          errorHandlerRef.current?.(error);
        }
      });
    };

    const appStateSubscription = appState.addEventListener("change", (nextState) => {
      const nextIsActive = nextState === "active";
      if (!mounted || nextIsActive === appIsActive) {
        return;
      }

      appIsActive = nextIsActive;
      if (appIsActive) {
        startCoordinator();
      } else {
        coordinator.stop();
      }
    });

    if (appIsActive) {
      startCoordinator();
    } else {
      coordinator.stop();
    }

    return () => {
      mounted = false;
      appStateSubscription.remove();
      unsubscribeCoordinator();
      coordinator.stop();
    };
  }, [appState, coordinatorFactory, householdId]);

  return snapshot;
}
