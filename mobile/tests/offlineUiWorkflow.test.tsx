import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { PropsWithChildren, useEffect, useMemo } from "react";
import { AppStateStatus, Button, Text, View } from "react-native";
import { I18nextProvider } from "react-i18next";

import { ConflictReviewPanel } from "../src/components/ConflictReviewPanel";
import {
  ConnectivityMonitor,
  ConnectivityStatus,
} from "../src/features/offline/connectivity";
import {
  createGroceryMutationReplayRunner,
  GroceryMutationHttpClient,
} from "../src/features/offline/groceryMutationReplayRunner";
import { LocalDatabaseConnection } from "../src/features/offline/localDatabase";
import {
  CachedGroceryItem,
  CachedShoppingSession,
} from "../src/features/offline/localGroceryCacheRepository";
import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";
import {
  applyOptimisticGroceryUpdate,
  GroceryQueryItem,
} from "../src/features/offline/optimisticGroceryUpdates";
import { HouseholdSyncCoordinator } from "../src/features/offline/syncCoordinator";
import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  AuthenticatedGrocerySyncDependencies,
  useAuthenticatedGrocerySync,
} from "../src/hooks/useAuthenticatedGrocerySync";
import {
  GroceryConflictReviewDependencies,
  useGroceryConflictReview,
} from "../src/hooks/useGroceryConflictReview";
import { SyncLifecycleAppState } from "../src/hooks/useHouseholdSyncLifecycle";
import { createAppI18n } from "../src/locales/i18n";

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";
const mutationId = "55555555-5555-4555-8555-555555555555";
const otherMutationId = "66666666-6666-4666-8666-666666666666";
const accessToken = "offline-ui-access-token";
const baseUpdatedAt = "2026-08-08T08:00:00Z";
const queryClients: QueryClient[] = [];

const cachedSession: CachedShoppingSession = {
  id: sessionId,
  householdId,
  createdByUserId: null,
  status: "active",
  createdAt: "2026-08-08T07:30:00Z",
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
  createdByUserId: null,
  assignedToUserId: null,
  completedByUserId: null,
  createdAt: "2026-08-08T07:35:00Z",
  updatedAt: baseUpdatedAt,
  completedAt: null,
  syncedAt: "2026-08-08T08:01:00Z",
};

afterEach(() => {
  queryClients.splice(0).forEach((queryClient) => queryClient.clear());
});

class MutableConnectivityMonitor implements ConnectivityMonitor {
  private readonly listeners = new Set<(status: ConnectivityStatus) => void>();

  constructor(private current: ConnectivityStatus) {}

  async getCurrentStatus(): Promise<ConnectivityStatus> {
    return this.current;
  }

  subscribe(listener: (status: ConnectivityStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(status: ConnectivityStatus): void {
    this.current = status;
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

class InMemoryMutationQueue {
  private readonly mutations = new Map<string, QueuedOfflineMutation>();

  async enqueue(mutation: QueuedOfflineMutation): Promise<void> {
    this.mutations.set(mutation.mutationId, mutation);
  }

  async listPending(household: string): Promise<QueuedOfflineMutation[]> {
    return this.list(household, "pending");
  }

  async listRequiresReview(household: string): Promise<QueuedOfflineMutation[]> {
    return this.list(household, "requires_review");
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

  async resolveReviewByKeepingServerVersion(
    household: string,
    mutation: string,
  ): Promise<void> {
    const current = this.requireScoped(household, mutation);
    if (current.status === "requires_review") {
      this.mutations.delete(mutation);
    }
  }

  get(mutation: string): QueuedOfflineMutation | undefined {
    return this.mutations.get(mutation);
  }

  private list(
    household: string,
    status: QueuedOfflineMutation["status"],
  ): QueuedOfflineMutation[] {
    return [...this.mutations.values()]
      .filter(
        (mutation) => mutation.householdId === household && mutation.status === status,
      )
      .sort(
        (left, right) =>
          left.createdAt.localeCompare(right.createdAt) ||
          left.mutationId.localeCompare(right.mutationId),
      );
  }

  private requireScoped(household: string, mutation: string): QueuedOfflineMutation {
    const current = this.mutations.get(mutation);
    if (current === undefined || current.householdId !== household) {
      throw new Error("The test mutation is unavailable.");
    }
    return current;
  }

  private removeScoped(household: string, mutation: string): void {
    this.requireScoped(household, mutation);
    this.mutations.delete(mutation);
  }
}

class FakeGroceryServer {
  readonly fetchItems = jest.fn(async (): Promise<readonly GroceryQueryItem[]> =>
    this.items.map((item) => ({ ...item })),
  );
  readonly httpClient: jest.Mocked<GroceryMutationHttpClient>;

  constructor(
    private items: GroceryQueryItem[],
    private editStatus: number = 200,
  ) {
    this.httpClient = {
      post: jest.fn().mockResolvedValue({ status: 201 }),
      patch: jest.fn(async (_url, data, _config) => {
        if (this.editStatus >= 400) {
          throw { isAxiosError: true, response: { status: this.editStatus } };
        }
        const changes = data as Readonly<{ name?: unknown }>;
        if (typeof changes.name === "string") {
          this.items = this.items.map((item) =>
            item.id === itemId
              ? {
                  ...item,
                  name: changes.name as string,
                  updatedAt: "2026-08-08T08:10:00Z",
                  syncedAt: "2026-08-08T08:10:01Z",
                }
              : item,
          );
        }
        return { status: 200 };
      }),
      delete: jest.fn().mockResolvedValue({ status: 204 }),
    };
  }
}

type WorkflowScreenProps = Readonly<{
  queue: InMemoryMutationQueue;
  monitor: MutableConnectivityMonitor;
  appState: FakeAppState;
  server: FakeGroceryServer;
}>;

function WorkflowScreen({ queue, monitor, appState, server }: WorkflowScreenProps) {
  const queryClient = useQueryClient();
  const cacheRepository = useMemo(
    () => ({
      getSession: jest.fn().mockResolvedValue(cachedSession),
      listItems: jest.fn().mockResolvedValue([cachedItem]),
    }),
    [],
  );
  const syncDependencies = useMemo<AuthenticatedGrocerySyncDependencies>(
    () => ({
      openDatabase: async () => ({}) as LocalDatabaseConnection,
      createCacheRepository: () => cacheRepository,
      createQueueRepository: () => queue,
      createConnectivityMonitor: () => monitor,
      createReplayRunner: (options) =>
        createGroceryMutationReplayRunner({
          ...options,
          httpClient: server.httpClient,
        }),
      createCoordinator: (currentHouseholdId, connectivity, runner) =>
        new HouseholdSyncCoordinator(currentHouseholdId, connectivity, runner),
    }),
    [cacheRepository, monitor, queue, server.httpClient],
  );
  const conflictDependencies = useMemo<GroceryConflictReviewDependencies>(
    () => ({ getRepository: async () => queue }),
    [queue],
  );
  const synchronization = useAuthenticatedGrocerySync({
    accessToken,
    householdId,
    shoppingSessionId: sessionId,
    dependencies: syncDependencies,
    appState,
  });
  const query = useQuery<readonly GroceryQueryItem[]>({
    queryKey: groceryQueryKeys.items(householdId, sessionId),
    queryFn: server.fetchItems,
    enabled: synchronization.synchronization.connectivity === "online",
    retry: false,
  });
  const conflictReview = useGroceryConflictReview({
    householdId,
    dependencies: conflictDependencies,
  });
  const refreshConflicts = conflictReview.refresh;

  useEffect(() => {
    if (synchronization.synchronization.status === "requires_review") {
      void refreshConflicts();
    }
  }, [refreshConflicts, synchronization.synchronization.status]);

  const editOffline = async (): Promise<void> => {
    const current = query.data?.find((item) => item.id === itemId);
    if (current === undefined) {
      return;
    }
    const mutation: QueuedOfflineMutation = {
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      operation: "edit",
      payload: { name: "Brown rice" },
      baseUpdatedAt: current.updatedAt,
      createdAt: "2026-08-08T08:02:00Z",
      attemptCount: 0,
      status: "pending",
      lastErrorCode: null,
    };
    await queue.enqueue(mutation);
    await applyOptimisticGroceryUpdate(queryClient, {
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      operation: "edit",
      occurredAt: mutation.createdAt,
      changes: { name: "Brown rice" },
    });
  };

  return (
    <View>
      <Text accessibilityRole="header">Grocery list</Text>
      <Text>Sync status: {synchronization.synchronization.status}</Text>
      {(query.data ?? []).map((item) => (
        <View key={item.id}>
          <Text>{item.name}</Text>
          {item.pendingMutation ? <Text>Waiting to sync</Text> : null}
        </View>
      ))}
      <Button onPress={() => void editOffline()} title="Edit rice offline" />
      <ConflictReviewPanel
        conflicts={conflictReview.conflicts}
        error={conflictReview.error}
        loading={conflictReview.loading}
        onKeepFamilyVersion={conflictReview.keepFamilyVersion}
        onReviewChange={() => undefined}
        resolvingMutationId={conflictReview.resolvingMutationId}
      />
    </View>
  );
}

function createQueryClient(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClients.push(queryClient);
  return queryClient;
}

function renderWorkflow(props: WorkflowScreenProps): QueryClient {
  const queryClient = createQueryClient();
  function Wrapper({ children }: PropsWithChildren) {
    return (
      <I18nextProvider i18n={createAppI18n("en")}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </I18nextProvider>
    );
  }
  render(<WorkflowScreen {...props} />, { wrapper: Wrapper });
  return queryClient;
}

function serverItem(name: string, updatedAt: string = baseUpdatedAt): GroceryQueryItem {
  return { ...cachedItem, name, updatedAt };
}

function otherHouseholdMutation(): QueuedOfflineMutation {
  return {
    mutationId: otherMutationId,
    householdId: otherHouseholdId,
    shoppingSessionId: sessionId,
    itemId,
    operation: "delete",
    payload: {},
    baseUpdatedAt,
    createdAt: "2026-08-08T08:03:00Z",
    attemptCount: 0,
    status: "pending",
    lastErrorCode: null,
  };
}

describe("end-to-end rendered offline grocery workflows", () => {
  it("shows an offline edit immediately and synchronizes it after reconnecting", async () => {
    const queue = new InMemoryMutationQueue();
    await queue.enqueue(otherHouseholdMutation());
    const monitor = new MutableConnectivityMonitor("offline");
    const appState = new FakeAppState("active");
    const server = new FakeGroceryServer([serverItem("Rice")]);
    renderWorkflow({ queue, monitor, appState, server });

    await waitFor(() => expect(screen.getByText("Rice")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "Edit rice offline" }));
    await waitFor(() => expect(screen.getByText("Brown rice")).toBeTruthy());
    expect(screen.getByText("Waiting to sync")).toBeTruthy();

    act(() => monitor.emit("online"));

    await waitFor(() => expect(queue.get(mutationId)).toBeUndefined());
    await waitFor(() => expect(screen.queryByText("Waiting to sync")).toBeNull());
    expect(screen.getByText("Brown rice")).toBeTruthy();
    expect(queue.get(otherMutationId)).toBeDefined();
    expect(server.httpClient.patch).toHaveBeenCalledWith(
      expect.stringContaining(`/items/${itemId}`),
      { name: "Brown rice" },
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Idempotency-Key": mutationId,
          "X-Base-Updated-At": baseUpdatedAt,
        },
      },
    );
  });

  it("shows a stale change and lets the member keep the newer family version", async () => {
    const queue = new InMemoryMutationQueue();
    const monitor = new MutableConnectivityMonitor("offline");
    const appState = new FakeAppState("active");
    const server = new FakeGroceryServer(
      [serverItem("Family rice", "2026-08-08T08:09:00Z")],
      412,
    );
    renderWorkflow({ queue, monitor, appState, server });
    await waitFor(() => expect(screen.getByText("Rice")).toBeTruthy());

    fireEvent.press(screen.getByRole("button", { name: "Edit rice offline" }));
    await waitFor(() => expect(screen.getByText("Brown rice")).toBeTruthy());
    act(() => monitor.emit("online"));

    await waitFor(() => expect(screen.getByText("Edit: Brown rice")).toBeTruthy());
    expect(screen.getByText("Family rice")).toBeTruthy();
    expect(screen.queryByText("412")).toBeNull();
    expect(queue.get(mutationId)?.status).toBe("requires_review");

    fireEvent.press(screen.getByRole("button", { name: "Keep family version" }));

    await waitFor(() => expect(queue.get(mutationId)).toBeUndefined());
    await waitFor(() =>
      expect(screen.getByText("No changes need review.")).toBeTruthy(),
    );
    expect(screen.getByText("Family rice")).toBeTruthy();
  });

  it("waits in the background and replays after foreground recovery", async () => {
    const queue = new InMemoryMutationQueue();
    const monitor = new MutableConnectivityMonitor("offline");
    const appState = new FakeAppState("background");
    const server = new FakeGroceryServer([serverItem("Rice")]);
    renderWorkflow({ queue, monitor, appState, server });
    await waitFor(() => expect(screen.getByText("Rice")).toBeTruthy());

    fireEvent.press(screen.getByRole("button", { name: "Edit rice offline" }));
    await waitFor(() => expect(queue.get(mutationId)).toBeDefined());
    act(() => monitor.emit("online"));
    await act(async () => Promise.resolve());
    expect(server.httpClient.patch).not.toHaveBeenCalled();
    expect(queue.get(mutationId)).toBeDefined();

    act(() => appState.transitionTo("active"));

    await waitFor(() => expect(server.httpClient.patch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(queue.get(mutationId)).toBeUndefined());
    expect(screen.getByText("Brown rice")).toBeTruthy();
  });
});
