export const groceryQueryKeys = {
  all: ["grocery"] as const,
  household: (householdId: string) =>
    [...groceryQueryKeys.all, "household", householdId] as const,
  session: (householdId: string, shoppingSessionId: string) =>
    [...groceryQueryKeys.household(householdId), "session", shoppingSessionId] as const,
  items: (householdId: string, shoppingSessionId: string) =>
    [...groceryQueryKeys.session(householdId, shoppingSessionId), "items"] as const,
  activity: (householdId: string, shoppingSessionId: string) =>
    [...groceryQueryKeys.session(householdId, shoppingSessionId), "activity"] as const,
  item: (householdId: string, shoppingSessionId: string, groceryItemId: string) =>
    [
      ...groceryQueryKeys.items(householdId, shoppingSessionId),
      "detail",
      groceryItemId,
    ] as const,
};
