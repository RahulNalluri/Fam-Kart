import { QueryClient, QueryKey } from "@tanstack/react-query";

import { groceryQueryKeys } from "../grocery/queryKeys";
import { CachedGroceryItem } from "./localGroceryCacheRepository";
import { OfflineMutationOperation } from "./synchronizationPolicy";

export type GroceryQueryItem = Omit<CachedGroceryItem, "syncedAt"> &
  Readonly<{
    syncedAt: string | null;
    pendingMutation?: Readonly<{
      id: string;
      operation: OfflineMutationOperation;
    }>;
  }>;

type MutationScope = Readonly<{
  mutationId: string;
  householdId: string;
  shoppingSessionId: string;
  itemId: string;
  occurredAt: string;
}>;

export type OptimisticGroceryMutation =
  | (MutationScope &
      Readonly<{
        operation: "add";
        item: Readonly<{
          name: string;
          quantity: string | null;
          unit: string | null;
          notes: string | null;
          createdByUserId: string | null;
          assignedToUserId: string | null;
        }>;
      }>)
  | (MutationScope &
      Readonly<{
        operation: "edit";
        changes: Readonly<
          Partial<
            Pick<
              GroceryQueryItem,
              "name" | "quantity" | "unit" | "notes" | "assignedToUserId"
            >
          >
        >;
      }>)
  | (MutationScope &
      Readonly<{
        operation: "complete";
        completedByUserId: string;
      }>)
  | (MutationScope & Readonly<{ operation: "reopen" | "delete" }>);

export type OptimisticGroceryUpdateContext = Readonly<{
  mutationId: string;
  operation: OfflineMutationOperation;
  householdId: string;
  shoppingSessionId: string;
  itemId: string;
  itemsQueryKey: QueryKey;
  itemQueryKey: QueryKey;
  previousItems: readonly GroceryQueryItem[];
  optimisticItems: readonly GroceryQueryItem[];
  optimisticDataUpdateCount: number;
  previousItem: GroceryQueryItem | undefined;
  previousDetail: GroceryQueryItem | undefined;
  optimisticItem: GroceryQueryItem | undefined;
}>;

export class OptimisticGroceryItemNotFoundError extends Error {
  constructor() {
    super("The grocery item is no longer available for this change.");
    this.name = "OptimisticGroceryItemNotFoundError";
  }
}

function compareItems(left: GroceryQueryItem, right: GroceryQueryItem): number {
  if (left.status !== right.status) {
    return left.status === "pending" ? -1 : 1;
  }
  return (
    left.createdAt.localeCompare(right.createdAt) || left.id.localeCompare(right.id)
  );
}

function markPending(
  item: GroceryQueryItem,
  mutation: OptimisticGroceryMutation,
): GroceryQueryItem {
  return {
    ...item,
    updatedAt: mutation.occurredAt,
    syncedAt: null,
    pendingMutation: {
      id: mutation.mutationId,
      operation: mutation.operation,
    },
  };
}

function buildOptimisticItem(
  currentItem: GroceryQueryItem | undefined,
  mutation: OptimisticGroceryMutation,
): GroceryQueryItem | undefined {
  if (mutation.operation === "add") {
    return markPending(
      {
        id: mutation.itemId,
        householdId: mutation.householdId,
        shoppingSessionId: mutation.shoppingSessionId,
        ...mutation.item,
        status: "pending",
        completedByUserId: null,
        createdAt: mutation.occurredAt,
        updatedAt: mutation.occurredAt,
        completedAt: null,
        syncedAt: null,
      },
      mutation,
    );
  }

  if (currentItem === undefined) {
    throw new OptimisticGroceryItemNotFoundError();
  }

  if (mutation.operation === "delete") {
    return undefined;
  }

  if (mutation.operation === "edit") {
    return markPending({ ...currentItem, ...mutation.changes }, mutation);
  }

  if (mutation.operation === "complete") {
    return markPending(
      {
        ...currentItem,
        status: "completed",
        completedByUserId: mutation.completedByUserId,
        completedAt: mutation.occurredAt,
      },
      mutation,
    );
  }

  return markPending(
    {
      ...currentItem,
      status: "pending",
      completedByUserId: null,
      completedAt: null,
    },
    mutation,
  );
}

function replaceItem(
  items: readonly GroceryQueryItem[],
  itemId: string,
  replacement: GroceryQueryItem | undefined,
): GroceryQueryItem[] {
  const remaining = items.filter((item) => item.id !== itemId);
  return (replacement === undefined ? remaining : [...remaining, replacement]).sort(
    compareItems,
  );
}

export async function applyOptimisticGroceryUpdate(
  queryClient: QueryClient,
  mutation: OptimisticGroceryMutation,
): Promise<OptimisticGroceryUpdateContext> {
  const itemsQueryKey = groceryQueryKeys.items(
    mutation.householdId,
    mutation.shoppingSessionId,
  );
  const itemQueryKey = groceryQueryKeys.item(
    mutation.householdId,
    mutation.shoppingSessionId,
    mutation.itemId,
  );

  await Promise.all([
    queryClient.cancelQueries({ queryKey: itemsQueryKey, exact: true }),
    queryClient.cancelQueries({ queryKey: itemQueryKey, exact: true }),
  ]);

  const previousItems =
    queryClient.getQueryData<readonly GroceryQueryItem[]>(itemsQueryKey) ?? [];
  const previousDetail = queryClient.getQueryData<GroceryQueryItem>(itemQueryKey);
  const previousItem =
    previousItems.find((item) => item.id === mutation.itemId) ?? previousDetail;
  const optimisticItem = buildOptimisticItem(previousItem, mutation);
  const optimisticItems = replaceItem(previousItems, mutation.itemId, optimisticItem);

  queryClient.setQueryData(itemsQueryKey, optimisticItems);
  const optimisticDataUpdateCount =
    queryClient.getQueryState(itemsQueryKey)?.dataUpdateCount;
  if (optimisticDataUpdateCount === undefined) {
    throw new Error("The optimistic grocery cache update could not be recorded.");
  }
  if (optimisticItem === undefined) {
    queryClient.removeQueries({ queryKey: itemQueryKey, exact: true });
  } else {
    queryClient.setQueryData(itemQueryKey, optimisticItem);
  }

  return {
    mutationId: mutation.mutationId,
    operation: mutation.operation,
    householdId: mutation.householdId,
    shoppingSessionId: mutation.shoppingSessionId,
    itemId: mutation.itemId,
    itemsQueryKey,
    itemQueryKey,
    previousItems,
    optimisticItems,
    optimisticDataUpdateCount,
    previousItem,
    previousDetail,
    optimisticItem,
  };
}

export function rollbackOptimisticGroceryUpdate(
  queryClient: QueryClient,
  context: OptimisticGroceryUpdateContext,
): boolean {
  if (
    queryClient.getQueryState(context.itemsQueryKey)?.dataUpdateCount !==
    context.optimisticDataUpdateCount
  ) {
    return false;
  }

  queryClient.setQueryData(context.itemsQueryKey, context.previousItems);
  if (context.previousDetail === undefined) {
    queryClient.removeQueries({ queryKey: context.itemQueryKey, exact: true });
  } else {
    queryClient.setQueryData(context.itemQueryKey, context.previousDetail);
  }
  return true;
}

export function confirmOptimisticGroceryUpdate(
  queryClient: QueryClient,
  context: OptimisticGroceryUpdateContext,
  serverItem?: CachedGroceryItem,
): boolean {
  if (
    queryClient.getQueryState(context.itemsQueryKey)?.dataUpdateCount !==
    context.optimisticDataUpdateCount
  ) {
    return false;
  }

  if (context.operation === "delete") {
    return true;
  }
  if (serverItem === undefined) {
    throw new Error("A successful grocery mutation must include the server item.");
  }
  if (
    serverItem.householdId !== context.householdId ||
    serverItem.shoppingSessionId !== context.shoppingSessionId
  ) {
    throw new Error("The server grocery item does not match the optimistic scope.");
  }

  const confirmedItem: GroceryQueryItem = { ...serverItem };
  const confirmedItems = replaceItem(
    context.optimisticItems,
    context.itemId,
    confirmedItem,
  );
  queryClient.setQueryData(context.itemsQueryKey, confirmedItems);
  if (serverItem.id !== context.itemId) {
    queryClient.removeQueries({ queryKey: context.itemQueryKey, exact: true });
  }
  queryClient.setQueryData(
    groceryQueryKeys.item(
      context.householdId,
      context.shoppingSessionId,
      serverItem.id,
    ),
    confirmedItem,
  );
  return true;
}
