import { QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AppStateStatus } from "react-native";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  ConnectivityMonitor,
  ConnectivityStatus,
} from "../src/features/offline/connectivity";
import { hydrateGroceryQueryCache } from "../src/features/offline/groceryCacheHydration";
import {
  CachedGroceryItem,
  CachedShoppingSession,
} from "../src/features/offline/localGroceryCacheRepository";
import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";
import {
  applyOptimisticGroceryUpdate,
  GroceryQueryItem,
} from "../src/features/offline/optimisticGroceryUpdates";
import {
  applyServerReconciliation,
  decideServerReconciliation,
} from "../src/features/offline/serverReconciliation";
import {
  HouseholdSyncCoordinator,
  HouseholdSyncRunner,
  SyncRunResult,
} from "../src/features/offline/syncCoordinator";
import {
  HouseholdSyncCoordinatorFactory,
  SyncLifecycleAppState,
  useHouseholdSyncLifecycle,
} from "../src/hooks/useHouseholdSyncLifecycle";

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";
const userId = "55555555-5555-4555-8555-555555555555";
const mutationId = "66666666-6666-4666-8666-666666666666";
const baseUpdatedAt = "2026-08-08T08:00:00Z";

const cachedSession: CachedShoppingSession = {
  id: sessionId,
  householdId,
  createdByUserId: userId,
  status: "active",
  createdAt: "2026-08-08T07:00:00Z",
  completedAt: null,
  syncedAt: "2026-08-08T08:01:00Z",
};

const cachedItem: CachedGroceryItem = {
  id: itemId,
  householdId,
  shoppingSessionId: sessionId,
  name: "Rice",
  quantity: "5.000",
  unit: "kg",
  notes: null,
  status: "pending",
  createdByUserId: userId,
  assignedToUserId: null,
  completedByUserId: null,
  createdAt: "2026-08-08T07:30:00Z",
  updatedAt: baseUpdatedAt,
  completedAt: null,
  syncedAt: "2026-08-08T08:01:00Z",
};

class InMemoryMutationQueue {
  private readonly mutations = new Map<string, QueuedOfflineMutation>();

  enqueue(mutation: QueuedOfflineMutation): void {
    this.mutations.set(mutation.mutationId, mutation);
  }

  listPending(household: string): QueuedOfflineMutation[] {
    return [...this.mutations.values()]
      .filter(
        (mutation) =>
          mutation.householdId === household && mutation.status === "pending",
      )
      .sort(
        (left, right) =>
          left.createdAt.localeCompare(right.createdAt) ||
          left.mutationId.localeCompare(right.mutationId),
      );
  }

  get(mutation: string): QueuedOfflineMutation | undefined {
    return this.mutations.get(mutation);
  }

  async recordRetry(
    household: string,
    mutation: string,
    errorCode: string,
  ): Promise<void> {
    const current = this.requireScoped(household, mutation);
    this.mutations.set(mutation, {
      ...current,
      attemptCount: current.attemptCount + 1,
      status: "pending",
      lastErrorCode: errorCode,
    });
  }

  async requireReview(
    household: string,
    mutation: string,
    errorCode: string,
  ): Promise<void> {
    const current = this.requireScoped(household, mutation);
    this.mutations.set(mutation, {
      ...current,
      status: "requires_review",
      lastErrorCode: errorCode,
    });
  }

  async removeAcknowledged(household: string, mutation: string): Promise<void> {
    this.removeScoped(household, mutation);
  }

  async removeDiscarded(household: string, mutation: string): Promise<void> {
    this.removeScoped(household, mutation);
  }

  private requireScoped(household: string, mutation: string): QueuedOfflineMutation {
    const current = this.mutations.get(mutation);
    if (current === undefined || current.householdId !== household) {
      throw new Error("The workflow queue mutation is unavailable.");
    }
    return current;
  }

  private removeScoped(household: string, mutation: string): void {
    this.requireScoped(household, mutation);
    this.mutations.delete(mutation);
  }
}

class MutableConnectivityMonitor implements ConnectivityMonitor {
  private readonly listeners = new Set<(status: ConnectivityStatus) => void>();

  constructor(private status: ConnectivityStatus) {}

  getCurrentStatus(): Promise<ConnectivityStatus> {
    return Promise.resolve(this.status);
  }

  subscribe(listener: (status: ConnectivityStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(status: ConnectivityStatus): void {
    this.status = status;
    this.listeners.forEach((listener) => listener(status));
  }
}

class FakeAppState implements SyncLifecycleAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();

  constructor(public currentState: AppStateStatus) {}

  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void } {
    this.listeners.add(listener);
    return { remove: () => this.listeners.delete(listener) };
  }

  transitionTo(state: AppStateStatus): void {
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

async function hydrateCachedList(queryClient: QueryClient): Promise<void> {
  await hydrateGroceryQueryCache(
    queryClient,
    {
      getSession: jest.fn().mockResolvedValue(cachedSession),
      listItems: jest.fn().mockResolvedValue([cachedItem]),
    },
    householdId,
    sessionId,
  );
}

function queuedMutation(
  operation: QueuedOfflineMutation["operation"] = "edit",
  household: string = householdId,
  id: string = mutationId,
): QueuedOfflineMutation {
  return {
    mutationId: id,
    householdId: household,
    shoppingSessionId: sessionId,
    itemId,
    operation,
    payload: operation === "edit" ? { name: "Brown rice" } : {},
    baseUpdatedAt,
    createdAt: "2026-08-08T08:05:00Z",
    attemptCount: 0,
    status: "pending",
    lastErrorCode: null,
  };
}

async function applyOfflineEdit(queryClient: QueryClient): Promise<void> {
  await applyOptimisticGroceryUpdate(queryClient, {
    operation: "edit",
    mutationId,
    householdId,
    shoppingSessionId: sessionId,
    itemId,
    occurredAt: "2026-08-08T08:05:00Z",
    changes: { name: "Brown rice" },
  });
}

function buildRunner(
  queue: InMemoryMutationQueue,
  queryClient: QueryClient,
  statuses: readonly (number | undefined)[],
  authoritativeItems: readonly CachedGroceryItem[],
): jest.MockedFunction<HouseholdSyncRunner> {
  let responseIndex = 0;
  return jest.fn(async (household): Promise<SyncRunResult> => {
    const pending = queue.listPending(household);
    if (pending.length === 0) {
      return { outcome: "nothing_to_sync", processedCount: 0 };
    }

    let processedCount = 0;
    for (const mutation of pending) {
      const statusCode = statuses[responseIndex];
      responseIndex += 1;
      const result = await applyServerReconciliation(
        mutation,
        decideServerReconciliation(mutation, statusCode),
        queue,
        async (refreshHouseholdId, refreshSessionId) => {
          queryClient.setQueryData(
            groceryQueryKeys.items(refreshHouseholdId, refreshSessionId),
            authoritativeItems,
          );
        },
      );
      processedCount += result.processedCount;
      if (result.outcome !== "synchronized") {
        return { ...result, processedCount };
      }
    }

    return { outcome: "synchronized", processedCount };
  });
}

function getItems(queryClient: QueryClient, household: string = householdId) {
  return (
    queryClient.getQueryData<readonly GroceryQueryItem[]>(
      groceryQueryKeys.items(household, sessionId),
    ) ?? []
  );
}

describe("complete offline grocery workflows", () => {
  it("hydrates, updates optimistically, and reconciles after reconnecting", async () => {
    const queryClient = createQueryClient();
    const queue = new InMemoryMutationQueue();
    await hydrateCachedList(queryClient);
    await applyOfflineEdit(queryClient);
    queue.enqueue(queuedMutation());
    expect(getItems(queryClient)[0]).toEqual(
      expect.objectContaining({
        name: "Brown rice",
        pendingMutation: { id: mutationId, operation: "edit" },
      }),
    );

    const serverItem: CachedGroceryItem = {
      ...cachedItem,
      name: "Brown rice",
      updatedAt: "2026-08-08T08:06:00Z",
      syncedAt: "2026-08-08T08:06:01Z",
    };
    const monitor = new MutableConnectivityMonitor("offline");
    const runner = buildRunner(queue, queryClient, [200], [serverItem]);
    const coordinator = new HouseholdSyncCoordinator(householdId, monitor, runner);
    await coordinator.start();
    expect(coordinator.getSnapshot().status).toBe("waiting_for_connection");

    monitor.emit("online");
    await waitFor(() => expect(queue.get(mutationId)).toBeUndefined());

    expect(getItems(queryClient)).toEqual([serverItem]);
    expect(getItems(queryClient)[0].pendingMutation).toBeUndefined();
    expect(coordinator.getSnapshot()).toEqual({
      connectivity: "online",
      status: "idle",
      lastProcessedCount: 1,
    });
    coordinator.stop();
    queryClient.clear();
  });

  it("keeps a stale completion for review and refreshes newer family data", async () => {
    const queryClient = createQueryClient();
    const queue = new InMemoryMutationQueue();
    await hydrateCachedList(queryClient);
    await applyOptimisticGroceryUpdate(queryClient, {
      operation: "complete",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt: "2026-08-08T08:05:00Z",
      completedByUserId: userId,
    });
    queue.enqueue(queuedMutation("complete"));

    const newerServerItem: CachedGroceryItem = {
      ...cachedItem,
      name: "Basmati rice",
      notes: "Updated by another member",
      updatedAt: "2026-08-08T08:07:00Z",
      syncedAt: "2026-08-08T08:07:01Z",
    };
    const coordinator = new HouseholdSyncCoordinator(
      householdId,
      new MutableConnectivityMonitor("online"),
      buildRunner(queue, queryClient, [412], [newerServerItem]),
    );
    await coordinator.start();

    expect(queue.get(mutationId)).toEqual(
      expect.objectContaining({
        status: "requires_review",
        lastErrorCode: "server_conflict",
      }),
    );
    expect(queue.listPending(householdId)).toEqual([]);
    expect(getItems(queryClient)).toEqual([newerServerItem]);
    expect(coordinator.getSnapshot().status).toBe("requires_review");
    coordinator.stop();
    queryClient.clear();
  });

  it("retries a temporary failure only after foreground lifecycle recovery", async () => {
    const queryClient = createQueryClient();
    const queue = new InMemoryMutationQueue();
    await hydrateCachedList(queryClient);
    await applyOfflineEdit(queryClient);
    queue.enqueue(queuedMutation());
    const serverItem: CachedGroceryItem = {
      ...cachedItem,
      name: "Brown rice",
      updatedAt: "2026-08-08T08:08:00Z",
      syncedAt: "2026-08-08T08:08:01Z",
    };
    const monitor = new MutableConnectivityMonitor("online");
    const runner = buildRunner(queue, queryClient, [undefined, 200], [serverItem]);
    const appState = new FakeAppState("active");
    const coordinatorFactory: HouseholdSyncCoordinatorFactory = (id) =>
      new HouseholdSyncCoordinator(id, monitor, runner);
    const { result, unmount } = renderHook(() =>
      useHouseholdSyncLifecycle({
        householdId,
        appState,
        coordinatorFactory,
      }),
    );

    await waitFor(() => expect(result.current.status).toBe("retry_waiting"));
    expect(queue.get(mutationId)).toEqual(
      expect.objectContaining({
        attemptCount: 1,
        lastErrorCode: "network_unavailable",
      }),
    );
    act(() => appState.transitionTo("background"));
    expect(result.current.status).toBe("stopped");
    expect(runner).toHaveBeenCalledTimes(1);

    act(() => appState.transitionTo("active"));
    await waitFor(() => expect(queue.get(mutationId)).toBeUndefined());

    expect(runner).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("idle");
    expect(getItems(queryClient)).toEqual([serverItem]);
    unmount();
    queryClient.clear();
  });

  it("keeps another household's cache and queued work isolated", async () => {
    const queryClient = createQueryClient();
    const queue = new InMemoryMutationQueue();
    const otherMutationId = "77777777-7777-4777-8777-777777777777";
    const otherItem = { ...cachedItem, householdId: otherHouseholdId, name: "Milk" };
    queryClient.setQueryData(groceryQueryKeys.items(otherHouseholdId, sessionId), [
      otherItem,
    ]);
    await hydrateCachedList(queryClient);
    await applyOfflineEdit(queryClient);
    queue.enqueue(queuedMutation());
    queue.enqueue(queuedMutation("edit", otherHouseholdId, otherMutationId));
    const serverItem = {
      ...cachedItem,
      name: "Brown rice",
      updatedAt: "2026-08-08T08:09:00Z",
    };
    const coordinator = new HouseholdSyncCoordinator(
      householdId,
      new MutableConnectivityMonitor("online"),
      buildRunner(queue, queryClient, [200], [serverItem]),
    );

    await coordinator.start();

    expect(queue.get(mutationId)).toBeUndefined();
    expect(queue.get(otherMutationId)).toBeDefined();
    expect(getItems(queryClient, otherHouseholdId)).toEqual([otherItem]);
    coordinator.stop();
    queryClient.clear();
  });
});
