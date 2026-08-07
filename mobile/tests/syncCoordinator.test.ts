import {
  ConnectivityMonitor,
  ConnectivityStatus,
} from "../src/features/offline/connectivity";
import {
  HouseholdSyncCoordinator,
  HouseholdSyncRunner,
  SyncRunResult,
} from "../src/features/offline/syncCoordinator";

const householdId = "11111111-1111-4111-8111-111111111111";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function flushPromises(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

class FakeConnectivityMonitor implements ConnectivityMonitor {
  private listener: ((status: ConnectivityStatus) => void) | null = null;
  readonly unsubscribe = jest.fn();

  constructor(
    private readonly initialStatus: ConnectivityStatus | Promise<ConnectivityStatus>,
  ) {}

  getCurrentStatus(): Promise<ConnectivityStatus> {
    return Promise.resolve(this.initialStatus);
  }

  subscribe(listener: (status: ConnectivityStatus) => void): () => void {
    this.listener = listener;
    return () => {
      this.listener = null;
      this.unsubscribe();
    };
  }

  emit(status: ConnectivityStatus): void {
    this.listener?.(status);
  }
}

const nothingToSync: SyncRunResult = {
  outcome: "nothing_to_sync",
  processedCount: 0,
};

describe("HouseholdSyncCoordinator", () => {
  it("waits offline and synchronizes after connectivity returns", async () => {
    const monitor = new FakeConnectivityMonitor("offline");
    const runner = jest
      .fn<ReturnType<HouseholdSyncRunner>, Parameters<HouseholdSyncRunner>>()
      .mockResolvedValue({ outcome: "synchronized", processedCount: 3 });
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);

    await coordinator.start();
    expect(coordinator.getSnapshot()).toEqual({
      connectivity: "offline",
      status: "waiting_for_connection",
      lastProcessedCount: 0,
    });
    expect(runner).not.toHaveBeenCalled();

    monitor.emit("online");
    await flushPromises();
    expect(runner).toHaveBeenCalledWith(householdId);
    expect(coordinator.getSnapshot()).toEqual({
      connectivity: "online",
      status: "idle",
      lastProcessedCount: 3,
    });
  });

  it("synchronizes immediately when startup connectivity is online", async () => {
    const monitor = new FakeConnectivityMonitor("online");
    const runner = jest.fn().mockResolvedValue(nothingToSync);
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);

    await coordinator.start();

    expect(runner).toHaveBeenCalledTimes(1);
    expect(coordinator.getSnapshot().status).toBe("idle");
  });

  it("coalesces overlapping requests and performs one requested follow-up", async () => {
    const monitor = new FakeConnectivityMonitor("online");
    const firstRun = deferred<SyncRunResult>();
    const runner = jest
      .fn()
      .mockReturnValueOnce(firstRun.promise)
      .mockResolvedValueOnce(nothingToSync);
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    const startPromise = coordinator.start();
    await flushPromises();
    expect(runner).toHaveBeenCalledTimes(1);

    const firstRequest = coordinator.requestSync();
    const secondRequest = coordinator.requestSync();
    expect(firstRequest).toBe(secondRequest);
    expect(runner).toHaveBeenCalledTimes(1);

    firstRun.resolve({ outcome: "synchronized", processedCount: 1 });
    await startPromise;
    await firstRequest;
    expect(runner).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["retry_later", "retry_waiting"],
    ["authentication_required", "authentication_required"],
    ["requires_review", "requires_review"],
  ] as const)("maps %s outcomes to %s", async (outcome, expectedStatus) => {
    const monitor = new FakeConnectivityMonitor("online");
    const runner = jest.fn().mockResolvedValue({ outcome, processedCount: 1 });
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);

    await coordinator.start();

    expect(coordinator.getSnapshot().status).toBe(expectedStatus);
    expect(coordinator.getSnapshot().lastProcessedCount).toBe(1);
  });

  it("keeps a blocking state when the monitor repeats the same online event", async () => {
    const monitor = new FakeConnectivityMonitor("online");
    const runner = jest.fn().mockResolvedValue({
      outcome: "authentication_required",
      processedCount: 0,
    });
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    await coordinator.start();

    monitor.emit("online");
    await flushPromises();

    expect(coordinator.getSnapshot().status).toBe("authentication_required");
    expect(runner).toHaveBeenCalledTimes(1);
  });

  it("reports controlled error state when the runner throws", async () => {
    const monitor = new FakeConnectivityMonitor("online");
    const runner = jest.fn().mockRejectedValue(new Error("private server detail"));
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    const snapshots: unknown[] = [];
    coordinator.subscribe((snapshot) => snapshots.push(snapshot));

    await coordinator.start();

    expect(coordinator.getSnapshot().status).toBe("error");
    expect(JSON.stringify(snapshots)).not.toContain("private server detail");
  });

  it("uses a newer listener event instead of a late initial connectivity result", async () => {
    const initial = deferred<ConnectivityStatus>();
    const monitor = new FakeConnectivityMonitor(initial.promise);
    const runner = jest.fn().mockResolvedValue(nothingToSync);
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    const startPromise = coordinator.start();

    monitor.emit("online");
    await flushPromises();
    initial.resolve("offline");
    await startPromise;

    expect(coordinator.getSnapshot().connectivity).toBe("online");
    expect(runner).toHaveBeenCalledTimes(1);
  });

  it("cleans up and ignores a late runner result after stop", async () => {
    const monitor = new FakeConnectivityMonitor("online");
    const run = deferred<SyncRunResult>();
    const runner = jest.fn().mockReturnValue(run.promise);
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    const startPromise = coordinator.start();
    await flushPromises();

    coordinator.stop();
    expect(coordinator.getSnapshot().status).toBe("stopped");
    expect(monitor.unsubscribe).toHaveBeenCalledTimes(1);

    run.resolve({ outcome: "synchronized", processedCount: 9 });
    await startPromise;
    expect(coordinator.getSnapshot()).toEqual({
      connectivity: "unknown",
      status: "stopped",
      lastProcessedCount: 0,
    });
  });

  it("notifies subscribers and supports listener cleanup", async () => {
    const monitor = new FakeConnectivityMonitor("offline");
    const coordinator = new HouseholdSyncCoordinator(
      householdId,
      monitor,
      jest.fn().mockResolvedValue(nothingToSync),
    );
    const listener = jest.fn();
    const unsubscribe = coordinator.subscribe(listener);

    await coordinator.start();
    const callsBeforeCleanup = listener.mock.calls.length;
    unsubscribe();
    monitor.emit("online");
    await flushPromises();

    expect(callsBeforeCleanup).toBeGreaterThan(0);
    expect(listener).toHaveBeenCalledTimes(callsBeforeCleanup);
  });
});
