import { ConnectivityMonitor, ConnectivityStatus } from "./connectivity";

export type SyncRunOutcome =
  | "synchronized"
  | "nothing_to_sync"
  | "retry_later"
  | "authentication_required"
  | "requires_review";

export type SyncRunResult = Readonly<{
  outcome: SyncRunOutcome;
  processedCount: number;
}>;

export type HouseholdSyncRunner = (householdId: string) => Promise<SyncRunResult>;

export type SyncCoordinatorStatus =
  | "stopped"
  | "checking_connectivity"
  | "waiting_for_connection"
  | "idle"
  | "syncing"
  | "retry_waiting"
  | "authentication_required"
  | "requires_review"
  | "error";

export type SyncCoordinatorSnapshot = Readonly<{
  connectivity: ConnectivityStatus;
  status: SyncCoordinatorStatus;
  lastProcessedCount: number;
}>;

type SnapshotListener = (snapshot: SyncCoordinatorSnapshot) => void;

const INITIAL_SNAPSHOT: SyncCoordinatorSnapshot = Object.freeze({
  connectivity: "unknown",
  status: "stopped",
  lastProcessedCount: 0,
});

function statusForOutcome(outcome: SyncRunOutcome): SyncCoordinatorStatus {
  switch (outcome) {
    case "synchronized":
    case "nothing_to_sync":
      return "idle";
    case "retry_later":
      return "retry_waiting";
    case "authentication_required":
      return "authentication_required";
    case "requires_review":
      return "requires_review";
  }
}

function validateSyncResult(result: SyncRunResult): void {
  if (!Number.isInteger(result.processedCount) || result.processedCount < 0) {
    throw new Error("A synchronization result has an invalid processed count.");
  }
}

export class HouseholdSyncCoordinator {
  private snapshot: SyncCoordinatorSnapshot = INITIAL_SNAPSHOT;
  private readonly listeners = new Set<SnapshotListener>();
  private unsubscribeConnectivity: (() => void) | null = null;
  private active = false;
  private generation = 0;
  private connectivityRevision = 0;
  private syncRequested = false;
  private syncPromise: Promise<void> | null = null;

  constructor(
    private readonly householdId: string,
    private readonly connectivityMonitor: ConnectivityMonitor,
    private readonly runSync: HouseholdSyncRunner,
  ) {
    if (!householdId.trim()) {
      throw new Error("A household is required for offline synchronization.");
    }
  }

  getSnapshot = (): SyncCoordinatorSnapshot => this.snapshot;

  subscribe = (listener: SnapshotListener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  async start(): Promise<void> {
    if (this.active) {
      return;
    }

    this.active = true;
    const generation = ++this.generation;
    const initialRevision = this.connectivityRevision;
    this.updateSnapshot({
      connectivity: "unknown",
      status: "checking_connectivity",
      lastProcessedCount: 0,
    });

    this.unsubscribeConnectivity = this.connectivityMonitor.subscribe((status) => {
      this.connectivityRevision += 1;
      void this.handleConnectivityChange(status, generation);
    });

    try {
      const initialStatus = await this.connectivityMonitor.getCurrentStatus();
      if (this.isCurrent(generation) && this.connectivityRevision === initialRevision) {
        await this.handleConnectivityChange(initialStatus, generation);
      }
    } catch {
      if (this.isCurrent(generation) && this.connectivityRevision === initialRevision) {
        this.updateSnapshot({
          ...this.snapshot,
          connectivity: "unknown",
          status: "error",
        });
      }
    }
  }

  stop(): void {
    if (!this.active) {
      return;
    }

    this.active = false;
    this.generation += 1;
    this.syncRequested = false;
    this.syncPromise = null;
    this.unsubscribeConnectivity?.();
    this.unsubscribeConnectivity = null;
    this.updateSnapshot(INITIAL_SNAPSHOT);
  }

  requestSync(): Promise<void> {
    if (!this.active) {
      return Promise.resolve();
    }

    if (this.snapshot.connectivity !== "online") {
      this.updateSnapshot({
        ...this.snapshot,
        status: "waiting_for_connection",
      });
      return Promise.resolve();
    }

    this.syncRequested = true;
    if (this.syncPromise !== null) {
      return this.syncPromise;
    }

    const generation = this.generation;
    const promise = this.drainSyncRequests(generation);
    this.syncPromise = promise;
    void promise.finally(() => {
      if (this.syncPromise === promise) {
        this.syncPromise = null;
      }
    });
    return promise;
  }

  private async handleConnectivityChange(
    connectivity: ConnectivityStatus,
    generation: number,
  ): Promise<void> {
    if (!this.isCurrent(generation)) {
      return;
    }

    const previousConnectivity = this.snapshot.connectivity;
    if (connectivity !== "online") {
      this.updateSnapshot({
        ...this.snapshot,
        connectivity,
        status: "waiting_for_connection",
      });
      return;
    }

    this.updateSnapshot({
      ...this.snapshot,
      connectivity,
      status: previousConnectivity === "online" ? this.snapshot.status : "idle",
    });
    if (previousConnectivity !== "online") {
      await this.requestSync();
    }
  }

  private async drainSyncRequests(generation: number): Promise<void> {
    while (
      this.isCurrent(generation) &&
      this.snapshot.connectivity === "online" &&
      this.syncRequested
    ) {
      this.syncRequested = false;
      this.updateSnapshot({ ...this.snapshot, status: "syncing" });

      let result: SyncRunResult;
      try {
        result = await this.runSync(this.householdId);
        validateSyncResult(result);
      } catch {
        if (this.isCurrent(generation)) {
          this.syncRequested = false;
          this.updateSnapshot({
            ...this.snapshot,
            status:
              this.snapshot.connectivity === "online"
                ? "error"
                : "waiting_for_connection",
          });
        }
        return;
      }

      if (!this.isCurrent(generation)) {
        return;
      }
      if (this.snapshot.connectivity !== "online") {
        this.updateSnapshot({
          ...this.snapshot,
          status: "waiting_for_connection",
        });
        return;
      }

      this.updateSnapshot({
        ...this.snapshot,
        status: statusForOutcome(result.outcome),
        lastProcessedCount: result.processedCount,
      });

      if (
        result.outcome === "retry_later" ||
        result.outcome === "authentication_required" ||
        result.outcome === "requires_review"
      ) {
        this.syncRequested = false;
        return;
      }
    }
  }

  private isCurrent(generation: number): boolean {
    return this.active && this.generation === generation;
  }

  private updateSnapshot(snapshot: SyncCoordinatorSnapshot): void {
    if (
      snapshot.connectivity === this.snapshot.connectivity &&
      snapshot.status === this.snapshot.status &&
      snapshot.lastProcessedCount === this.snapshot.lastProcessedCount
    ) {
      return;
    }

    this.snapshot = Object.freeze(snapshot);
    for (const listener of this.listeners) {
      listener(this.snapshot);
    }
  }
}
