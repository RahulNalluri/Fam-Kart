import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { PropsWithChildren } from "react";
import { AppStateStatus } from "react-native";

import {
  ConnectivityMonitor,
  ConnectivityStatus,
} from "../src/features/offline/connectivity";
import { GroceryMutationReplayRunnerOptions } from "../src/features/offline/groceryMutationReplayRunner";
import { LocalDatabaseConnection } from "../src/features/offline/localDatabase";
import {
  CachedGroceryItem,
  CachedShoppingSession,
} from "../src/features/offline/localGroceryCacheRepository";
import {
  HouseholdSyncRunner,
  SyncCoordinatorSnapshot,
} from "../src/features/offline/syncCoordinator";
import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  AuthenticatedGrocerySyncDependencies,
  useAuthenticatedGrocerySync,
} from "../src/hooks/useAuthenticatedGrocerySync";
import {
  SyncLifecycleAppState,
  SyncLifecycleCoordinator,
} from "../src/hooks/useHouseholdSyncLifecycle";

const householdId = "11111111-1111-4111-8111-111111111111";
const secondHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const secondSessionId = "44444444-4444-4444-8444-444444444444";
const accessToken = "authenticated-access-token";
const stoppedSnapshot: SyncCoordinatorSnapshot = {
  connectivity: "unknown",
  status: "stopped",
  lastProcessedCount: 0,
};
const queryClients: QueryClient[] = [];

afterEach(() => {
  queryClients.splice(0).forEach((queryClient) => queryClient.clear());
});

const cachedSession: CachedShoppingSession = {
  id: sessionId,
  householdId,
  createdByUserId: null,
  status: "active",
  createdAt: "2026-08-08T08:00:00Z",
  completedAt: null,
  syncedAt: "2026-08-08T08:05:00Z",
};

const cachedItem: CachedGroceryItem = {
  id: "55555555-5555-4555-8555-555555555555",
  householdId,
  shoppingSessionId: sessionId,
  name: "Milk",
  quantity: "2.000",
  unit: "packet",
  notes: null,
  status: "pending",
  createdByUserId: null,
  assignedToUserId: null,
  completedByUserId: null,
  createdAt: "2026-08-08T08:01:00Z",
  updatedAt: "2026-08-08T08:02:00Z",
  completedAt: null,
  syncedAt: "2026-08-08T08:05:00Z",
};

class FakeAppState implements SyncLifecycleAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();

  constructor(public currentState: AppStateStatus = "active") {}

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

class FakeCoordinator implements SyncLifecycleCoordinator {
  private readonly listeners = new Set<(snapshot: SyncCoordinatorSnapshot) => void>();
  readonly start = jest.fn(async () => undefined);
  readonly stop = jest.fn();

  getSnapshot(): SyncCoordinatorSnapshot {
    return stoppedSnapshot;
  }

  subscribe(listener: (snapshot: SyncCoordinatorSnapshot) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

class OnlineMonitor implements ConnectivityMonitor {
  async getCurrentStatus(): Promise<ConnectivityStatus> {
    return "online";
  }

  subscribe(): () => void {
    return () => undefined;
  }
}

function createQueryClient(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClients.push(queryClient);
  return queryClient;
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function buildHarness() {
  const appState = new FakeAppState("active");
  const database = {} as LocalDatabaseConnection;
  const cacheRepository = {
    getSession: jest.fn().mockResolvedValue(cachedSession),
    listItems: jest.fn().mockResolvedValue([cachedItem]),
  };
  const queueRepository: GroceryMutationReplayRunnerOptions["queue"] = {
    listPending: jest.fn().mockResolvedValue([]),
    recordRetry: jest.fn().mockResolvedValue(undefined),
    requireReview: jest.fn().mockResolvedValue(undefined),
    removeAcknowledged: jest.fn().mockResolvedValue(undefined),
    removeDiscarded: jest.fn().mockResolvedValue(undefined),
  };
  const connectivityMonitor = new OnlineMonitor();
  const runner: jest.MockedFunction<HouseholdSyncRunner> = jest
    .fn()
    .mockResolvedValue({ outcome: "nothing_to_sync", processedCount: 0 });
  const coordinators: FakeCoordinator[] = [];
  const openDatabase = jest.fn().mockResolvedValue(database);
  const createCacheRepository = jest.fn(() => cacheRepository);
  const createQueueRepository = jest.fn(() => queueRepository);
  const createConnectivityMonitor = jest.fn(() => connectivityMonitor);
  const createReplayRunner: jest.MockedFunction<
    AuthenticatedGrocerySyncDependencies["createReplayRunner"]
  > = jest.fn((options: GroceryMutationReplayRunnerOptions) => {
    void options;
    return runner;
  });
  const createCoordinator: jest.MockedFunction<
    AuthenticatedGrocerySyncDependencies["createCoordinator"]
  > = jest.fn(
    (
      _currentHouseholdId: string,
      _currentMonitor: ConnectivityMonitor,
      _currentRunner: HouseholdSyncRunner,
    ) => {
      const coordinator = new FakeCoordinator();
      coordinators.push(coordinator);
      return coordinator;
    },
  );
  const dependencies: AuthenticatedGrocerySyncDependencies = {
    openDatabase,
    createCacheRepository,
    createQueueRepository,
    createConnectivityMonitor,
    createReplayRunner,
    createCoordinator,
  };

  return {
    appState,
    cacheRepository,
    queueRepository,
    connectivityMonitor,
    runner,
    coordinators,
    openDatabase,
    createCacheRepository,
    createQueueRepository,
    createConnectivityMonitor,
    createReplayRunner,
    createCoordinator,
    dependencies,
  };
}

describe("authenticated grocery synchronization integration", () => {
  it("stays disabled and does not open SQLite without authenticated scope", () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useAuthenticatedGrocerySync({
          accessToken: null,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          appState: harness.appState,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    expect(result.current).toEqual({
      status: "disabled",
      hydration: null,
      synchronization: stoppedSnapshot,
    });
    expect(harness.openDatabase).not.toHaveBeenCalled();
  });

  it("hydrates the selected cached list before mounting synchronization", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useAuthenticatedGrocerySync({
          accessToken,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          appState: harness.appState,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    expect(result.current.status).toBe("initializing");
    await waitFor(() => expect(result.current.status).toBe("ready"));

    expect(result.current.hydration).toEqual({
      status: "hydrated",
      itemCount: 1,
      syncedAt: cachedSession.syncedAt,
    });
    expect(
      queryClient.getQueryData(groceryQueryKeys.items(householdId, sessionId)),
    ).toEqual([cachedItem]);
    expect(harness.createCoordinator).toHaveBeenCalledWith(
      householdId,
      harness.connectivityMonitor,
      harness.runner,
    );
    expect(harness.cacheRepository.listItems.mock.invocationCallOrder[0]).toBeLessThan(
      harness.createCoordinator.mock.invocationCallOrder[0],
    );
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalled());
  });

  it("provides the live access token and session-scoped refresh to the replay runner", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const invalidateQueries = jest.spyOn(queryClient, "invalidateQueries");
    const { rerender } = renderHook(
      ({ token }: { token: string }) =>
        useAuthenticatedGrocerySync({
          accessToken: token,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          appState: harness.appState,
        }),
      {
        initialProps: { token: accessToken },
        wrapper: createWrapper(queryClient),
      },
    );
    await waitFor(() => expect(harness.createReplayRunner).toHaveBeenCalledTimes(1));
    const replayOptions = harness.createReplayRunner.mock.calls[0][0];

    expect(replayOptions.queue).toBe(harness.queueRepository);
    expect(replayOptions.getAccessToken()).toBe(accessToken);
    rerender({ token: "refreshed-access-token" });
    expect(replayOptions.getAccessToken()).toBe("refreshed-access-token");
    expect(harness.openDatabase).toHaveBeenCalledTimes(1);

    await replayOptions.refreshServerState(householdId, sessionId);
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: groceryQueryKeys.session(householdId, sessionId),
    });
  });

  it("stops the previous coordinator and rehydrates when grocery scope changes", async () => {
    const harness = buildHarness();
    harness.cacheRepository.getSession.mockImplementation(
      async (currentHouseholdId: string, currentSessionId: string) => ({
        ...cachedSession,
        id: currentSessionId,
        householdId: currentHouseholdId,
      }),
    );
    harness.cacheRepository.listItems.mockResolvedValue([]);
    const queryClient = createQueryClient();
    const { rerender } = renderHook(
      ({
        currentHouseholdId,
        currentSessionId,
      }: {
        currentHouseholdId: string;
        currentSessionId: string;
      }) =>
        useAuthenticatedGrocerySync({
          accessToken,
          householdId: currentHouseholdId,
          shoppingSessionId: currentSessionId,
          dependencies: harness.dependencies,
          appState: harness.appState,
        }),
      {
        initialProps: { currentHouseholdId: householdId, currentSessionId: sessionId },
        wrapper: createWrapper(queryClient),
      },
    );
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));

    rerender({
      currentHouseholdId: secondHouseholdId,
      currentSessionId: secondSessionId,
    });

    expect(harness.coordinators[0].stop).toHaveBeenCalled();
    await waitFor(() => expect(harness.coordinators).toHaveLength(2));
    expect(harness.cacheRepository.getSession).toHaveBeenLastCalledWith(
      secondHouseholdId,
      secondSessionId,
    );
    expect(harness.createCoordinator).toHaveBeenLastCalledWith(
      secondHouseholdId,
      harness.connectivityMonitor,
      harness.runner,
    );
  });

  it("stops in the background and restarts after returning to the foreground", async () => {
    const harness = buildHarness();
    const appState = new FakeAppState("active");
    const queryClient = createQueryClient();
    renderHook(
      () =>
        useAuthenticatedGrocerySync({
          accessToken,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          appState,
        }),
      { wrapper: createWrapper(queryClient) },
    );
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(1));

    act(() => appState.transitionTo("background"));
    expect(harness.coordinators[0].stop).toHaveBeenCalledTimes(1);
    act(() => appState.transitionTo("active"));
    await waitFor(() => expect(harness.coordinators[0].start).toHaveBeenCalledTimes(2));
  });

  it("returns a controlled error when SQLite initialization fails", async () => {
    const harness = buildHarness();
    const privateError = new Error("private database path");
    harness.openDatabase.mockRejectedValueOnce(privateError);
    const onError = jest.fn();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useAuthenticatedGrocerySync({
          accessToken,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          onError,
          appState: harness.appState,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(onError).toHaveBeenCalledWith(privateError);
    expect(result.current.hydration).toBeNull();
    expect(JSON.stringify(result.current)).not.toContain("private database path");
    expect(harness.createCoordinator).not.toHaveBeenCalled();
  });

  it("does not start synchronization after cache hydration fails", async () => {
    const harness = buildHarness();
    const privateError = new Error("private cached grocery content");
    harness.cacheRepository.getSession.mockRejectedValueOnce(privateError);
    const onError = jest.fn();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useAuthenticatedGrocerySync({
          accessToken,
          householdId,
          shoppingSessionId: sessionId,
          dependencies: harness.dependencies,
          onError,
          appState: harness.appState,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(onError).toHaveBeenCalledWith(privateError);
    expect(harness.createCoordinator).not.toHaveBeenCalled();
  });
});
