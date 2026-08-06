import { QueryClient } from "@tanstack/react-query";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import { hydrateGroceryQueryCache } from "../src/features/offline/groceryCacheHydration";
import {
  CachedGroceryItem,
  CachedShoppingSession,
} from "../src/features/offline/localGroceryCacheRepository";

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const syncedAt = "2026-08-07T08:30:00Z";

const cachedSession: CachedShoppingSession = {
  id: sessionId,
  householdId,
  createdByUserId: null,
  status: "active",
  createdAt: "2026-08-07T08:00:00Z",
  completedAt: null,
  syncedAt,
};

const cachedItem: CachedGroceryItem = {
  id: "44444444-4444-4444-8444-444444444444",
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
  createdAt: "2026-08-07T08:05:00Z",
  updatedAt: "2026-08-07T08:10:00Z",
  completedAt: null,
  syncedAt,
};

function buildQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function buildRepository(items: CachedGroceryItem[] = [cachedItem]) {
  return {
    getSession: jest.fn().mockResolvedValue(cachedSession),
    listItems: jest.fn().mockResolvedValue(items),
  };
}

describe("React Query grocery cache hydration", () => {
  it("hydrates the scoped items query with the SQLite snapshot timestamp", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    const queryKey = groceryQueryKeys.items(householdId, sessionId);

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).resolves.toEqual({ status: "hydrated", itemCount: 1, syncedAt });

    expect(queryClient.getQueryData(queryKey)).toEqual([cachedItem]);
    expect(queryClient.getQueryState(queryKey)?.dataUpdatedAt).toBe(
      Date.parse(syncedAt),
    );
    queryClient.clear();
  });

  it("hydrates an intentionally empty cached snapshot", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository([]);
    const queryKey = groceryQueryKeys.items(householdId, sessionId);

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).resolves.toEqual({ status: "hydrated", itemCount: 0, syncedAt });

    expect(queryClient.getQueryData(queryKey)).toEqual([]);
    queryClient.clear();
  });

  it("does not create query data when no cached session exists", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    repository.getSession.mockResolvedValueOnce(null);

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).resolves.toEqual({ status: "not_cached" });

    expect(repository.listItems).not.toHaveBeenCalled();
    expect(
      queryClient.getQueryData(groceryQueryKeys.items(householdId, sessionId)),
    ).toBeUndefined();
    queryClient.clear();
  });

  it("keeps existing online query data without reading SQLite", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    const queryKey = groceryQueryKeys.items(householdId, sessionId);
    const onlineItems = [{ id: "online-item", name: "Rice" }];
    queryClient.setQueryData(queryKey, onlineItems);

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).resolves.toEqual({ status: "skipped_existing_data" });

    expect(repository.getSession).not.toHaveBeenCalled();
    expect(queryClient.getQueryData(queryKey)).toBe(onlineItems);
    queryClient.clear();
  });

  it("lets an online response win if it arrives during the SQLite read", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    const queryKey = groceryQueryKeys.items(householdId, sessionId);
    const onlineItems = [{ id: "online-item", name: "Onions" }];
    repository.listItems.mockImplementationOnce(async () => {
      queryClient.setQueryData(queryKey, onlineItems);
      return [cachedItem];
    });

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).resolves.toEqual({ status: "skipped_existing_data" });

    expect(queryClient.getQueryData(queryKey)).toBe(onlineItems);
    queryClient.clear();
  });

  it("does not change another household's items query", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    const otherKey = groceryQueryKeys.items(otherHouseholdId, sessionId);
    const otherItems = [{ id: "other-item", name: "Salt" }];
    queryClient.setQueryData(otherKey, otherItems);

    await hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId);

    expect(queryClient.getQueryData(otherKey)).toBe(otherItems);
    queryClient.clear();
  });

  it("propagates storage failures without creating partial query data", async () => {
    const queryClient = buildQueryClient();
    const repository = buildRepository();
    const storageError = new Error("storage unavailable");
    repository.listItems.mockRejectedValueOnce(storageError);

    await expect(
      hydrateGroceryQueryCache(queryClient, repository, householdId, sessionId),
    ).rejects.toBe(storageError);

    expect(
      queryClient.getQueryData(groceryQueryKeys.items(householdId, sessionId)),
    ).toBeUndefined();
    queryClient.clear();
  });
});
