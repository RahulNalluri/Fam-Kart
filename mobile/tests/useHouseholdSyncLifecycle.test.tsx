import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AppStateStatus } from "react-native";

import {
  ConnectivityMonitor,
  ConnectivityStatus,
} from "../src/features/offline/connectivity";
import {
  HouseholdSyncCoordinator,
  SyncCoordinatorSnapshot,
} from "../src/features/offline/syncCoordinator";
import {
  HouseholdSyncCoordinatorFactory,
  SyncLifecycleAppState,
  SyncLifecycleCoordinator,
  useHouseholdSyncLifecycle,
} from "../src/hooks/useHouseholdSyncLifecycle";

const householdId = "11111111-1111-4111-8111-111111111111";
const secondHouseholdId = "22222222-2222-4222-8222-222222222222";
const stoppedSnapshot: SyncCoordinatorSnapshot = {
  connectivity: "unknown",
  status: "stopped",
  lastProcessedCount: 0,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

class FakeAppState implements SyncLifecycleAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();
  readonly removeListener = jest.fn();

  constructor(public currentState: AppStateStatus) {}

  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void } {
    this.listeners.add(listener);
    return {
      remove: () => {
        this.listeners.delete(listener);
        this.removeListener();
      },
    };
  }

  transitionTo(state: AppStateStatus): void {
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }

  get listenerCount(): number {
    return this.listeners.size;
  }
}

class FakeCoordinator implements SyncLifecycleCoordinator {
  private snapshot = stoppedSnapshot;
  private readonly listeners = new Set<(snapshot: SyncCoordinatorSnapshot) => void>();
  readonly start = jest.fn(async () => undefined);
  readonly stop = jest.fn(() => {
    this.emit(stoppedSnapshot);
  });

  getSnapshot(): SyncCoordinatorSnapshot {
    return this.snapshot;
  }

  subscribe(listener: (snapshot: SyncCoordinatorSnapshot) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(snapshot: SyncCoordinatorSnapshot): void {
    this.snapshot = snapshot;
    this.listeners.forEach((listener) => listener(snapshot));
  }
}

class OnlineMonitor implements ConnectivityMonitor {
  getCurrentStatus(): Promise<ConnectivityStatus> {
    return Promise.resolve("online");
  }

  subscribe(): () => void {
    return () => undefined;
  }
}

function buildHarness(initialState: AppStateStatus = "active") {
  const appState = new FakeAppState(initialState);
  const coordinators: FakeCoordinator[] = [];
  const coordinatorFactory: HouseholdSyncCoordinatorFactory = jest.fn(() => {
    const coordinator = new FakeCoordinator();
    coordinators.push(coordinator);
    return coordinator;
  });
  return { appState, coordinators, coordinatorFactory };
}

describe("useHouseholdSyncLifecycle", () => {
  it("starts one household coordinator while the app is active", async () => {
    const harness = buildHarness();
    const { unmount } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );

    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));
    expect(harness.coordinatorFactory).toHaveBeenCalledWith(householdId);
    expect(harness.appState.listenerCount).toBe(1);
    unmount();
  });

  it("waits in the background and starts when the app enters the foreground", async () => {
    const harness = buildHarness("background");
    renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );
    expect(harness.coordinators[0].start).not.toHaveBeenCalled();

    act(() => harness.appState.transitionTo("active"));

    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));
  });

  it("stops once in the background and recovers once on foreground", async () => {
    const harness = buildHarness();
    renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));

    act(() => harness.appState.transitionTo("inactive"));
    act(() => harness.appState.transitionTo("background"));
    act(() => harness.appState.transitionTo("active"));
    act(() => harness.appState.transitionTo("active"));

    expect(harness.coordinators[0].stop).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(2));
  });

  it("exposes coordinator snapshots to the future status UI", () => {
    const harness = buildHarness();
    const { result } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );
    const syncing: SyncCoordinatorSnapshot = {
      connectivity: "online",
      status: "syncing",
      lastProcessedCount: 2,
    };

    act(() => harness.coordinators[0].emit(syncing));

    expect(result.current).toEqual(syncing);
  });

  it("replaces and cleans up the coordinator when the household changes", async () => {
    const harness = buildHarness();
    const { rerender } = renderHook(
      ({ currentHouseholdId }: { currentHouseholdId: string }) =>
        useHouseholdSyncLifecycle({
          householdId: currentHouseholdId,
          appState: harness.appState,
          coordinatorFactory: harness.coordinatorFactory,
        }),
      { initialProps: { currentHouseholdId: householdId } },
    );
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));

    rerender({ currentHouseholdId: secondHouseholdId });

    expect(harness.coordinators[0].stop).toHaveBeenCalledTimes(1);
    expect(harness.coordinatorFactory).toHaveBeenLastCalledWith(secondHouseholdId);
    await waitFor(() => expect(harness.coordinators[1].start).toHaveBeenCalledTimes(1));
  });

  it("removes listeners, stops on unmount, and ignores late snapshots", () => {
    const harness = buildHarness();
    const { result, unmount } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );
    const valueBeforeUnmount = result.current;

    unmount();
    act(() =>
      harness.coordinators[0].emit({
        connectivity: "online",
        status: "syncing",
        lastProcessedCount: 9,
      }),
    );

    expect(harness.appState.removeListener).toHaveBeenCalledTimes(1);
    expect(harness.appState.listenerCount).toBe(0);
    expect(harness.coordinators[0].stop).toHaveBeenCalledTimes(1);
    expect(result.current).toEqual(valueBeforeUnmount);
  });

  it("reports active startup failures without retaining technical details", async () => {
    const appState = new FakeAppState("active");
    const startError = new Error("private startup detail");
    const coordinator = new FakeCoordinator();
    coordinator.start.mockRejectedValueOnce(startError);
    const onError = jest.fn();
    const coordinatorFactory: HouseholdSyncCoordinatorFactory = () => coordinator;
    const { result } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState,
        coordinatorFactory,
        onError,
      }),
    );

    await waitFor(() => expect(onError).toHaveBeenCalledWith(startError));
    expect(result.current.status).toBe("error");
    expect(JSON.stringify(result.current)).not.toContain("private startup detail");
  });

  it("ignores a late startup failure after the app enters the background", async () => {
    const appState = new FakeAppState("active");
    const startup = deferred<undefined>();
    const coordinator = new FakeCoordinator();
    coordinator.start.mockReturnValueOnce(startup.promise);
    const coordinatorFactory: HouseholdSyncCoordinatorFactory = () => coordinator;
    const onError = jest.fn();
    const { result } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState,
        coordinatorFactory,
        onError,
      }),
    );

    act(() => appState.transitionTo("background"));
    await act(async () => {
      startup.reject(new Error("late background failure"));
      await Promise.resolve();
    });

    expect(onError).not.toHaveBeenCalled();
    expect(result.current).toEqual(stoppedSnapshot);
  });

  it("keeps synchronization stopped when no household is selected", () => {
    const harness = buildHarness();
    const { result } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId: null,
        appState: harness.appState,
        coordinatorFactory: harness.coordinatorFactory,
      }),
    );

    expect(result.current).toEqual(stoppedSnapshot);
    expect(harness.coordinatorFactory).not.toHaveBeenCalled();
  });

  it("runs real coordinator recovery after each foreground return", async () => {
    const appState = new FakeAppState("background");
    const runner = jest.fn().mockResolvedValue({
      outcome: "nothing_to_sync",
      processedCount: 0,
    });
    const coordinatorFactory: HouseholdSyncCoordinatorFactory = (id) =>
      new HouseholdSyncCoordinator(id, new OnlineMonitor(), runner);
    renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState,
        coordinatorFactory,
      }),
    );
    expect(runner).not.toHaveBeenCalled();

    act(() => appState.transitionTo("active"));
    await waitFor(() => expect(runner).toHaveBeenCalledTimes(1));
    act(() => appState.transitionTo("background"));
    act(() => appState.transitionTo("active"));

    await waitFor(() => expect(runner).toHaveBeenCalledTimes(2));
  });
});
