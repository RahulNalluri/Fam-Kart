import { QueryClient } from "@tanstack/react-query";

import { RealtimeEvent } from "../../types/realtime";
import { groceryQueryKeys } from "./queryKeys";

const ITEM_DETAIL_CHANGE_EVENTS = new Set<RealtimeEvent["event_type"]>([
  "grocery.item_edited",
  "grocery.item_completed",
  "grocery.item_reopened",
]);

export async function synchronizeGroceryRealtimeEvent(
  queryClient: QueryClient,
  event: RealtimeEvent,
): Promise<void> {
  const { shopping_session_id: sessionId, grocery_item_id: itemId } = event.payload;
  const itemKey = groceryQueryKeys.item(event.household_id, sessionId, itemId);

  if (event.event_type === "grocery.item_deleted") {
    queryClient.removeQueries({ queryKey: itemKey, exact: true });
  }

  const invalidations = [
    queryClient.invalidateQueries({
      queryKey: groceryQueryKeys.items(event.household_id, sessionId),
      exact: true,
    }),
    queryClient.invalidateQueries({
      queryKey: groceryQueryKeys.activity(event.household_id, sessionId),
      exact: true,
    }),
  ];

  if (ITEM_DETAIL_CHANGE_EVENTS.has(event.event_type)) {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: itemKey, exact: true }),
    );
  }

  await Promise.all(invalidations);
}

export async function refreshHouseholdGroceryQueries(
  queryClient: QueryClient,
  householdId: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: groceryQueryKeys.household(householdId),
  });
}

export async function refreshShoppingSessionGroceryQueries(
  queryClient: QueryClient,
  householdId: string,
  shoppingSessionId: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: groceryQueryKeys.session(householdId, shoppingSessionId),
  });
}
