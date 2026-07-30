import { QueryClient } from "@tanstack/react-query";

import { groceryQueryKeys } from "../src/features/grocery/queryKeys";
import { synchronizeGroceryRealtimeEvent } from "../src/features/grocery/realtimeSynchronization";
import { RealtimeEvent, RealtimeEventType } from "../src/types/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";
const otherHouseholdId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const otherSessionId = "44444444-4444-4444-8444-444444444444";
const itemId = "55555555-5555-4555-8555-555555555555";

function buildEvent(eventType: RealtimeEventType): RealtimeEvent {
  return {
    schema_version: 1,
    event_id: "66666666-6666-4666-8666-666666666666",
    event_type: eventType,
    household_id: householdId,
    occurred_at: "2026-07-30T12:00:00Z",
    payload: {
      shopping_session_id: sessionId,
      grocery_item_id: itemId,
      actor_user_id: "77777777-7777-4777-8777-777777777777",
      item_name: "Milk",
      sequence_number: 1,
    },
  };
}

function buildQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

describe("grocery real-time React Query synchronization", () => {
  it.each<RealtimeEventType>([
    "grocery.item_added",
    "grocery.item_edited",
    "grocery.item_completed",
    "grocery.item_reopened",
    "grocery.item_deleted",
  ])("invalidates the affected session for %s", async (eventType) => {
    const queryClient = buildQueryClient();
    const itemsKey = groceryQueryKeys.items(householdId, sessionId);
    const activityKey = groceryQueryKeys.activity(householdId, sessionId);
    const otherHouseholdKey = groceryQueryKeys.items(otherHouseholdId, sessionId);
    const otherSessionKey = groceryQueryKeys.items(householdId, otherSessionId);
    queryClient.setQueryData(itemsKey, ["Milk"]);
    queryClient.setQueryData(activityKey, []);
    queryClient.setQueryData(otherHouseholdKey, ["Rice"]);
    queryClient.setQueryData(otherSessionKey, ["Onions"]);

    await synchronizeGroceryRealtimeEvent(queryClient, buildEvent(eventType));

    expect(queryClient.getQueryState(itemsKey)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(activityKey)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(otherHouseholdKey)?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(otherSessionKey)?.isInvalidated).toBe(false);
    queryClient.clear();
  });

  it.each<RealtimeEventType>([
    "grocery.item_edited",
    "grocery.item_completed",
    "grocery.item_reopened",
  ])("invalidates affected item details for %s", async (eventType) => {
    const queryClient = buildQueryClient();
    const itemKey = groceryQueryKeys.item(householdId, sessionId, itemId);
    queryClient.setQueryData(itemKey, { id: itemId, name: "Milk" });

    await synchronizeGroceryRealtimeEvent(queryClient, buildEvent(eventType));

    expect(queryClient.getQueryState(itemKey)?.isInvalidated).toBe(true);
    queryClient.clear();
  });

  it("removes deleted item details from the cache", async () => {
    const queryClient = buildQueryClient();
    const itemKey = groceryQueryKeys.item(householdId, sessionId, itemId);
    queryClient.setQueryData(itemKey, { id: itemId, name: "Milk" });

    await synchronizeGroceryRealtimeEvent(
      queryClient,
      buildEvent("grocery.item_deleted"),
    );

    expect(queryClient.getQueryState(itemKey)).toBeUndefined();
    queryClient.clear();
  });
});
