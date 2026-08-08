import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { PropsWithChildren } from "react";

import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";
import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import {
  GroceryConflictReviewDependencies,
  useGroceryConflictReview,
} from "../src/hooks/useGroceryConflictReview";

const householdId = "11111111-1111-4111-8111-111111111111";
const secondHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const mutationId = "44444444-4444-4444-8444-444444444444";
const queryClients: QueryClient[] = [];

const conflict: QueuedOfflineMutation = {
  mutationId,
  householdId,
  shoppingSessionId: sessionId,
  itemId: "55555555-5555-4555-8555-555555555555",
  operation: "edit",
  payload: { name: "Brown rice", quantity: "5.000", unit: "kg" },
  baseUpdatedAt: "2026-08-08T08:00:00Z",
  createdAt: "2026-08-08T08:01:00Z",
  attemptCount: 1,
  status: "requires_review",
  lastErrorCode: "server_conflict",
};

afterEach(() => {
  queryClients.splice(0).forEach((queryClient) => queryClient.clear());
});

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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function buildHarness(reviewedMutations: QueuedOfflineMutation[] = [conflict]) {
  const repository = {
    listRequiresReview: jest.fn().mockResolvedValue(reviewedMutations),
    resolveReviewByKeepingServerVersion: jest.fn().mockResolvedValue(undefined),
  };
  const dependencies: GroceryConflictReviewDependencies = {
    getRepository: jest.fn().mockResolvedValue(repository),
  };
  return { repository, dependencies };
}

describe("grocery conflict review controller", () => {
  it("stays empty without opening SQLite when no household is selected", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId: null,
          dependencies: harness.dependencies,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.conflicts).toEqual([]);
    expect(harness.dependencies.getRepository).not.toHaveBeenCalled();
  });

  it("loads only reviewed mutations for the selected household", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId,
          dependencies: harness.dependencies,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.conflicts).toEqual([conflict]));
    expect(harness.repository.listRequiresReview).toHaveBeenCalledWith(householdId);
    expect(result.current.error).toBeNull();
  });

  it("refreshes authoritative session data before removing reviewed work", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const invalidateQueries = jest.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId,
          dependencies: harness.dependencies,
        }),
      { wrapper: createWrapper(queryClient) },
    );
    await waitFor(() => expect(result.current.conflicts).toHaveLength(1));

    await act(async () => {
      await expect(result.current.keepFamilyVersion(mutationId)).resolves.toBe(true);
    });

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: groceryQueryKeys.session(householdId, sessionId),
    });
    expect(harness.repository.resolveReviewByKeepingServerVersion).toHaveBeenCalledWith(
      householdId,
      mutationId,
    );
    expect(invalidateQueries.mock.invocationCallOrder[0]).toBeLessThan(
      harness.repository.resolveReviewByKeepingServerVersion.mock
        .invocationCallOrder[0],
    );
    expect(result.current.conflicts).toEqual([]);
  });

  it("keeps reviewed work when authoritative refresh fails", async () => {
    const harness = buildHarness();
    const queryClient = createQueryClient();
    const privateError = new Error("private refresh response");
    jest.spyOn(queryClient, "invalidateQueries").mockRejectedValueOnce(privateError);
    const onError = jest.fn();
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId,
          dependencies: harness.dependencies,
          onError,
        }),
      { wrapper: createWrapper(queryClient) },
    );
    await waitFor(() => expect(result.current.conflicts).toHaveLength(1));

    await act(async () => {
      await expect(result.current.keepFamilyVersion(mutationId)).resolves.toBe(false);
    });

    expect(result.current.error).toBe("resolve_failed");
    expect(result.current.conflicts).toEqual([conflict]);
    expect(onError).toHaveBeenCalledWith(privateError);
    expect(
      harness.repository.resolveReviewByKeepingServerVersion,
    ).not.toHaveBeenCalled();
    expect(JSON.stringify(result.current)).not.toContain("private refresh response");
  });

  it("reports a controlled load failure without retaining technical details", async () => {
    const harness = buildHarness();
    const privateError = new Error("private SQLite row");
    harness.repository.listRequiresReview.mockRejectedValueOnce(privateError);
    const onError = jest.fn();
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId,
          dependencies: harness.dependencies,
          onError,
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await waitFor(() => expect(result.current.error).toBe("load_failed"));
    expect(result.current.conflicts).toEqual([]);
    expect(onError).toHaveBeenCalledWith(privateError);
    expect(JSON.stringify(result.current)).not.toContain("private SQLite row");
  });

  it("ignores reviewed rows returned after the household changes", async () => {
    const harness = buildHarness();
    const firstLoad = deferred<QueuedOfflineMutation[]>();
    harness.repository.listRequiresReview
      .mockReturnValueOnce(firstLoad.promise)
      .mockResolvedValueOnce([]);
    const queryClient = createQueryClient();
    const { result, rerender } = renderHook(
      ({ currentHouseholdId }: { currentHouseholdId: string }) =>
        useGroceryConflictReview({
          householdId: currentHouseholdId,
          dependencies: harness.dependencies,
        }),
      {
        initialProps: { currentHouseholdId: householdId },
        wrapper: createWrapper(queryClient),
      },
    );

    rerender({ currentHouseholdId: secondHouseholdId });
    await waitFor(() =>
      expect(harness.repository.listRequiresReview).toHaveBeenCalledWith(
        secondHouseholdId,
      ),
    );
    await act(async () => {
      firstLoad.resolve([conflict]);
      await firstLoad.promise;
    });

    expect(result.current.conflicts).toEqual([]);
  });

  it("rejects unknown or concurrent resolution requests", async () => {
    const harness = buildHarness();
    const resolution = deferred<void>();
    harness.repository.resolveReviewByKeepingServerVersion.mockReturnValueOnce(
      resolution.promise,
    );
    const queryClient = createQueryClient();
    const { result } = renderHook(
      () =>
        useGroceryConflictReview({
          householdId,
          dependencies: harness.dependencies,
        }),
      { wrapper: createWrapper(queryClient) },
    );
    await waitFor(() => expect(result.current.conflicts).toHaveLength(1));

    await expect(result.current.keepFamilyVersion("unknown")).resolves.toBe(false);
    let firstResolution!: Promise<boolean>;
    act(() => {
      firstResolution = result.current.keepFamilyVersion(mutationId);
    });
    await waitFor(() => expect(result.current.resolvingMutationId).toBe(mutationId));
    await expect(result.current.keepFamilyVersion(mutationId)).resolves.toBe(false);
    await act(async () => {
      resolution.resolve();
      await firstResolution;
    });

    expect(
      harness.repository.resolveReviewByKeepingServerVersion,
    ).toHaveBeenCalledTimes(1);
  });
});
