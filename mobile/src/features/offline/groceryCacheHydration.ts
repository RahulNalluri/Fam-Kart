import { QueryClient } from "@tanstack/react-query";

import { groceryQueryKeys } from "../grocery/queryKeys";
import {
  CachedGroceryItem,
  LocalGroceryCacheRepository,
} from "./localGroceryCacheRepository";

type GroceryCacheReader = Pick<LocalGroceryCacheRepository, "getSession" | "listItems">;

export type GroceryCacheHydrationResult =
  | Readonly<{ status: "hydrated"; itemCount: number; syncedAt: string }>
  | Readonly<{ status: "not_cached" }>
  | Readonly<{ status: "skipped_existing_data" }>;

export async function hydrateGroceryQueryCache(
  queryClient: QueryClient,
  cacheRepository: GroceryCacheReader,
  householdId: string,
  shoppingSessionId: string,
): Promise<GroceryCacheHydrationResult> {
  const queryKey = groceryQueryKeys.items(householdId, shoppingSessionId);
  if (queryClient.getQueryData(queryKey) !== undefined) {
    return { status: "skipped_existing_data" };
  }

  const session = await cacheRepository.getSession(householdId, shoppingSessionId);
  if (session === null) {
    return { status: "not_cached" };
  }

  const items = await cacheRepository.listItems(householdId, shoppingSessionId);

  // An online query may finish while SQLite is being read. Online data always wins.
  if (queryClient.getQueryData(queryKey) !== undefined) {
    return { status: "skipped_existing_data" };
  }

  const synchronizedAt = Date.parse(session.syncedAt);
  queryClient.setQueryData<CachedGroceryItem[]>(queryKey, items, {
    updatedAt: Number.isNaN(synchronizedAt) ? 0 : synchronizedAt,
  });

  return {
    status: "hydrated",
    itemCount: items.length,
    syncedAt: session.syncedAt,
  };
}
