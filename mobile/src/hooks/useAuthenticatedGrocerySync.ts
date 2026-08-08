import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ConnectivityMonitor,
  ExpoConnectivityMonitor,
} from "../features/offline/connectivity";
import {
  GroceryCacheHydrationResult,
  hydrateGroceryQueryCache,
} from "../features/offline/groceryCacheHydration";
import {
  createGroceryMutationReplayRunner,
  GroceryMutationReplayRunnerOptions,
} from "../features/offline/groceryMutationReplayRunner";
import {
  getLocalDatabase,
  LocalDatabaseConnection,
} from "../features/offline/localDatabase";
import { LocalGroceryCacheRepository } from "../features/offline/localGroceryCacheRepository";
import { LocalMutationQueueRepository } from "../features/offline/localMutationQueueRepository";
import {
  HouseholdSyncCoordinator,
  HouseholdSyncRunner,
} from "../features/offline/syncCoordinator";
import { refreshShoppingSessionGroceryQueries } from "../features/grocery/realtimeSynchronization";
import {
  HouseholdSyncCoordinatorFactory,
  SyncLifecycleAppState,
  SyncLifecycleCoordinator,
  useHouseholdSyncLifecycle,
} from "./useHouseholdSyncLifecycle";

type GroceryCacheReader = Pick<LocalGroceryCacheRepository, "getSession" | "listItems">;

export type AuthenticatedGrocerySyncDependencies = Readonly<{
  openDatabase: () => Promise<LocalDatabaseConnection>;
  createCacheRepository: (database: LocalDatabaseConnection) => GroceryCacheReader;
  createQueueRepository: (
    database: LocalDatabaseConnection,
  ) => GroceryMutationReplayRunnerOptions["queue"];
  createConnectivityMonitor: () => ConnectivityMonitor;
  createReplayRunner: (
    options: GroceryMutationReplayRunnerOptions,
  ) => HouseholdSyncRunner;
  createCoordinator: (
    householdId: string,
    connectivityMonitor: ConnectivityMonitor,
    runner: HouseholdSyncRunner,
  ) => SyncLifecycleCoordinator;
}>;

export type AuthenticatedGrocerySyncStatus =
  "disabled" | "initializing" | "ready" | "error";

export type UseAuthenticatedGrocerySyncOptions = Readonly<{
  accessToken: string | null;
  householdId: string | null;
  shoppingSessionId: string | null;
  dependencies?: Partial<AuthenticatedGrocerySyncDependencies>;
  appState?: SyncLifecycleAppState;
  onError?: (error: unknown) => void;
}>;

export type AuthenticatedGrocerySyncState = Readonly<{
  status: AuthenticatedGrocerySyncStatus;
  hydration: GroceryCacheHydrationResult | null;
  synchronization: ReturnType<typeof useHouseholdSyncLifecycle>;
}>;

type PreparedSynchronization = Readonly<{
  scopeKey: string;
  cacheRepository: GroceryCacheReader;
  queueRepository: GroceryMutationReplayRunnerOptions["queue"];
  connectivityMonitor: ConnectivityMonitor;
  hydration: GroceryCacheHydrationResult;
}>;

function createCacheRepository(
  database: LocalDatabaseConnection,
): LocalGroceryCacheRepository {
  return new LocalGroceryCacheRepository(database);
}

function createQueueRepository(
  database: LocalDatabaseConnection,
): LocalMutationQueueRepository {
  return new LocalMutationQueueRepository(database);
}

const defaultDependencies: AuthenticatedGrocerySyncDependencies = {
  openDatabase: getLocalDatabase,
  createCacheRepository,
  createQueueRepository,
  createConnectivityMonitor: () => new ExpoConnectivityMonitor(),
  createReplayRunner: createGroceryMutationReplayRunner,
  createCoordinator: (householdId, connectivityMonitor, runner) =>
    new HouseholdSyncCoordinator(householdId, connectivityMonitor, runner),
};

const inactiveCoordinatorFactory: HouseholdSyncCoordinatorFactory = () => {
  throw new Error("Authenticated grocery synchronization is not ready.");
};

function buildScopeKey(householdId: string, shoppingSessionId: string): string {
  return `${householdId}\u0000${shoppingSessionId}`;
}

function buildCoordinatorFactory(
  queryClient: QueryClient,
  prepared: PreparedSynchronization,
  accessTokenRef: Readonly<{ current: string | null }>,
  dependencies: Pick<
    AuthenticatedGrocerySyncDependencies,
    "createReplayRunner" | "createCoordinator"
  >,
): HouseholdSyncCoordinatorFactory {
  return (householdId) => {
    const runner = dependencies.createReplayRunner({
      queue: prepared.queueRepository,
      getAccessToken: () => accessTokenRef.current,
      refreshServerState: (refreshHouseholdId, refreshShoppingSessionId) =>
        refreshShoppingSessionGroceryQueries(
          queryClient,
          refreshHouseholdId,
          refreshShoppingSessionId,
        ),
    });
    return dependencies.createCoordinator(
      householdId,
      prepared.connectivityMonitor,
      runner,
    );
  };
}

export function useAuthenticatedGrocerySync({
  accessToken,
  householdId,
  shoppingSessionId,
  dependencies,
  appState,
  onError,
}: UseAuthenticatedGrocerySyncOptions): AuthenticatedGrocerySyncState {
  const queryClient = useQueryClient();
  const accessTokenRef = useRef(accessToken);
  const errorHandlerRef = useRef(onError);
  accessTokenRef.current = accessToken;
  errorHandlerRef.current = onError;

  const openDatabase = dependencies?.openDatabase ?? defaultDependencies.openDatabase;
  const makeCacheRepository =
    dependencies?.createCacheRepository ?? defaultDependencies.createCacheRepository;
  const makeQueueRepository =
    dependencies?.createQueueRepository ?? defaultDependencies.createQueueRepository;
  const makeConnectivityMonitor =
    dependencies?.createConnectivityMonitor ??
    defaultDependencies.createConnectivityMonitor;
  const createReplayRunner =
    dependencies?.createReplayRunner ?? defaultDependencies.createReplayRunner;
  const createCoordinator =
    dependencies?.createCoordinator ?? defaultDependencies.createCoordinator;

  const authenticatedScopeAvailable = Boolean(
    accessToken?.trim() && householdId?.trim() && shoppingSessionId?.trim(),
  );
  const scopeKey =
    authenticatedScopeAvailable && householdId && shoppingSessionId
      ? buildScopeKey(householdId, shoppingSessionId)
      : null;
  const [status, setStatus] = useState<AuthenticatedGrocerySyncStatus>(
    authenticatedScopeAvailable ? "initializing" : "disabled",
  );
  const [prepared, setPrepared] = useState<PreparedSynchronization | null>(null);

  useEffect(() => {
    if (scopeKey === null || householdId === null || shoppingSessionId === null) {
      setPrepared(null);
      setStatus("disabled");
      return;
    }

    let active = true;
    setPrepared(null);
    setStatus("initializing");

    void (async () => {
      try {
        const database = await openDatabase();
        const cacheRepository = makeCacheRepository(database);
        const queueRepository = makeQueueRepository(database);
        const connectivityMonitor = makeConnectivityMonitor();
        const hydration = await hydrateGroceryQueryCache(
          queryClient,
          cacheRepository,
          householdId,
          shoppingSessionId,
        );

        if (active) {
          setPrepared({
            scopeKey,
            cacheRepository,
            queueRepository,
            connectivityMonitor,
            hydration,
          });
          setStatus("ready");
        }
      } catch (error) {
        if (active) {
          setPrepared(null);
          setStatus("error");
          errorHandlerRef.current?.(error);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [
    householdId,
    makeCacheRepository,
    makeConnectivityMonitor,
    makeQueueRepository,
    openDatabase,
    queryClient,
    scopeKey,
    shoppingSessionId,
  ]);

  const preparedForScope =
    prepared !== null && prepared.scopeKey === scopeKey ? prepared : null;
  const coordinatorFactory = useMemo(
    () =>
      preparedForScope === null
        ? inactiveCoordinatorFactory
        : buildCoordinatorFactory(queryClient, preparedForScope, accessTokenRef, {
            createReplayRunner,
            createCoordinator,
          }),
    [createCoordinator, createReplayRunner, preparedForScope, queryClient],
  );
  const synchronization = useHouseholdSyncLifecycle({
    householdId: preparedForScope === null ? null : householdId,
    coordinatorFactory,
    appState,
    onError,
  });

  return {
    status: scopeKey === null ? "disabled" : status,
    hydration: preparedForScope?.hydration ?? null,
    synchronization,
  };
}
