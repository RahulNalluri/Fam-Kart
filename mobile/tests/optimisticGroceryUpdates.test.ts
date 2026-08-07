import { QueryClient } from "@tanstack/react-query";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import { CachedGroceryItem } from "../src/features/offline/localGroceryCacheRepository";
import {
  applyOptimisticGroceryUpdate,
  confirmOptimisticGroceryUpdate,
  GroceryQueryItem,
  OptimisticGroceryItemNotFoundError,
  rollbackOptimisticGroceryUpdate,
} from "../src/features/offline/optimisticGroceryUpdates";

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";
const mutationId = "55555555-5555-4555-8555-555555555555";
const occurredAt = "2026-08-07T10:00:00Z";

const item: CachedGroceryItem = {
  id: itemId,
  householdId,
  shoppingSessionId: sessionId,
  name: "Milk",
  quantity: "2.000",
  unit: "packet",
  notes: null,
  status: "pending",
  createdByUserId: "66666666-6666-4666-8666-666666666666",
  assignedToUserId: null,
  completedByUserId: null,
  createdAt: "2026-08-07T08:00:00Z",
  updatedAt: "2026-08-07T08:00:00Z",
  completedAt: null,
  syncedAt: "2026-08-07T08:01:00Z",
};

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

function seedItems(
  queryClient: QueryClient,
  items: readonly GroceryQueryItem[] = [item],
) {
  queryClient.setQueryData(groceryQueryKeys.items(householdId, sessionId), items);
  if (items.some((current) => current.id === itemId)) {
    queryClient.setQueryData(
      groceryQueryKeys.item(householdId, sessionId, itemId),
      item,
    );
  } else {
    queryClient.removeQueries({
      queryKey: groceryQueryKeys.item(householdId, sessionId, itemId),
      exact: true,
    });
  }
}

function getItems(queryClient: QueryClient): readonly GroceryQueryItem[] {
  return queryClient.getQueryData(groceryQueryKeys.items(householdId, sessionId)) ?? [];
}

describe("optimistic grocery updates", () => {
  it("adds a pending local item immediately", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const optimisticItemId = "77777777-7777-4777-8777-777777777777";

    await applyOptimisticGroceryUpdate(queryClient, {
      operation: "add",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId: optimisticItemId,
      occurredAt,
      item: {
        name: "Rice",
        quantity: "5.000",
        unit: "kg",
        notes: null,
        createdByUserId: item.createdByUserId,
        assignedToUserId: null,
      },
    });

    expect(getItems(queryClient)).toContainEqual(
      expect.objectContaining({
        id: optimisticItemId,
        name: "Rice",
        syncedAt: null,
        pendingMutation: { id: mutationId, operation: "add" },
      }),
    );
  });

  it("optimistically edits an item and can restore the exact previous data", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "edit",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      changes: { name: "Low-fat milk", quantity: "1.000" },
    });

    expect(getItems(queryClient)[0]).toEqual(
      expect.objectContaining({
        name: "Low-fat milk",
        quantity: "1.000",
        pendingMutation: { id: mutationId, operation: "edit" },
      }),
    );
    expect(rollbackOptimisticGroceryUpdate(queryClient, context)).toBe(true);
    expect(getItems(queryClient)).toEqual([item]);
  });

  it("does not create a detail cache during rollback when none existed before", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(groceryQueryKeys.items(householdId, sessionId), [item]);
    const itemKey = groceryQueryKeys.item(householdId, sessionId, itemId);
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "edit",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      changes: { name: "Low-fat milk" },
    });

    expect(queryClient.getQueryData(itemKey)).toBeDefined();
    expect(rollbackOptimisticGroceryUpdate(queryClient, context)).toBe(true);
    expect(queryClient.getQueryData(itemKey)).toBeUndefined();
  });

  it("completes and reopens an item immediately with pending-first ordering", async () => {
    const queryClient = createQueryClient();
    const otherItem = {
      ...item,
      id: "88888888-8888-4888-8888-888888888888",
      name: "Salt",
    };
    seedItems(queryClient, [item, otherItem]);

    await applyOptimisticGroceryUpdate(queryClient, {
      operation: "complete",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      completedByUserId: item.createdByUserId!,
    });

    expect(getItems(queryClient).map((current) => current.id)).toEqual([
      otherItem.id,
      itemId,
    ]);
    expect(getItems(queryClient)[1]).toEqual(
      expect.objectContaining({ status: "completed", completedAt: occurredAt }),
    );

    const completedItem = getItems(queryClient)[1];
    const secondClient = createQueryClient();
    seedItems(secondClient, [completedItem]);
    await applyOptimisticGroceryUpdate(secondClient, {
      operation: "reopen",
      mutationId: "99999999-9999-4999-8999-999999999999",
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt: "2026-08-07T10:01:00Z",
    });

    expect(getItems(secondClient)[0]).toEqual(
      expect.objectContaining({
        status: "pending",
        completedAt: null,
        completedByUserId: null,
      }),
    );
  });

  it("deletes immediately and restores the item when the request fails", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "delete",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
    });

    expect(getItems(queryClient)).toEqual([]);
    expect(
      queryClient.getQueryData(groceryQueryKeys.item(householdId, sessionId, itemId)),
    ).toBeUndefined();
    expect(rollbackOptimisticGroceryUpdate(queryClient, context)).toBe(true);
    expect(getItems(queryClient)).toEqual([item]);
  });

  it("replaces a temporary add with the authoritative server item", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient, []);
    const temporaryId = "77777777-7777-4777-8777-777777777777";
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "add",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId: temporaryId,
      occurredAt,
      item: {
        name: "Rice",
        quantity: "5.000",
        unit: "kg",
        notes: null,
        createdByUserId: item.createdByUserId,
        assignedToUserId: null,
      },
    });
    const serverItem = { ...item, name: "Rice", quantity: "5.000", unit: "kg" };

    expect(confirmOptimisticGroceryUpdate(queryClient, context, serverItem)).toBe(true);
    expect(getItems(queryClient)).toEqual([serverItem]);
    expect(
      queryClient.getQueryData(
        groceryQueryKeys.item(householdId, sessionId, temporaryId),
      ),
    ).toBeUndefined();
  });

  it("rejects a server item from a different household scope", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "edit",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      changes: { name: "Fresh milk" },
    });

    expect(() =>
      confirmOptimisticGroceryUpdate(queryClient, context, {
        ...item,
        householdId: otherHouseholdId,
      }),
    ).toThrow("The server grocery item does not match the optimistic scope.");
    expect(getItems(queryClient)[0]).toEqual(
      expect.objectContaining({ name: "Fresh milk" }),
    );
  });

  it("does not touch another household or session", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const otherKey = groceryQueryKeys.items(otherHouseholdId, sessionId);
    const otherItems = [{ ...item, householdId: otherHouseholdId }];
    queryClient.setQueryData(otherKey, otherItems);

    await applyOptimisticGroceryUpdate(queryClient, {
      operation: "edit",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      changes: { name: "Fresh milk" },
    });

    expect(queryClient.getQueryData(otherKey)).toBe(otherItems);
  });

  it("rejects a change to an item missing from both list and detail caches", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient, []);

    await expect(
      applyOptimisticGroceryUpdate(queryClient, {
        operation: "edit",
        mutationId,
        householdId,
        shoppingSessionId: sessionId,
        itemId,
        occurredAt,
        changes: { name: "Fresh milk" },
      }),
    ).rejects.toBeInstanceOf(OptimisticGroceryItemNotFoundError);
  });

  it("does not roll stale data back over a newer server refresh", async () => {
    const queryClient = createQueryClient();
    seedItems(queryClient);
    const context = await applyOptimisticGroceryUpdate(queryClient, {
      operation: "edit",
      mutationId,
      householdId,
      shoppingSessionId: sessionId,
      itemId,
      occurredAt,
      changes: { name: "Fresh milk" },
    });
    const refreshedItems = [{ ...item, name: "Family pack milk" }];
    queryClient.setQueryData(context.itemsQueryKey, refreshedItems);

    expect(rollbackOptimisticGroceryUpdate(queryClient, context)).toBe(false);
    expect(getItems(queryClient)).toEqual(refreshedItems);
  });
});
