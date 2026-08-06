import { LocalDatabaseConnection } from "../src/features/offline/localDatabase";
import {
  CachedGroceryItem,
  GrocerySessionSnapshot,
  LocalGroceryCacheRepository,
} from "../src/features/offline/localGroceryCacheRepository";

const householdId = "11111111-1111-4111-8111-111111111111";
const sessionId = "22222222-2222-4222-8222-222222222222";
const itemId = "33333333-3333-4333-8333-333333333333";
const syncedAt = "2026-08-07T08:30:00Z";

const itemRow = {
  id: itemId,
  household_id: householdId,
  shopping_session_id: sessionId,
  name: "Rice",
  quantity: "5.000",
  unit: "kg",
  notes: null,
  status: "pending" as const,
  created_by_user_id: "44444444-4444-4444-8444-444444444444",
  assigned_to_user_id: null,
  completed_by_user_id: null,
  created_at: "2026-08-07T08:00:00Z",
  updated_at: "2026-08-07T08:15:00Z",
  completed_at: null,
  synced_at: syncedAt,
};

const expectedItem: CachedGroceryItem = {
  id: itemId,
  householdId,
  shoppingSessionId: sessionId,
  name: "Rice",
  quantity: "5.000",
  unit: "kg",
  notes: null,
  status: "pending",
  createdByUserId: "44444444-4444-4444-8444-444444444444",
  assignedToUserId: null,
  completedByUserId: null,
  createdAt: "2026-08-07T08:00:00Z",
  updatedAt: "2026-08-07T08:15:00Z",
  completedAt: null,
  syncedAt,
};

const snapshot: GrocerySessionSnapshot = {
  session: {
    id: sessionId,
    householdId,
    createdByUserId: "44444444-4444-4444-8444-444444444444",
    status: "active",
    createdAt: "2026-08-07T07:55:00Z",
    completedAt: null,
  },
  items: [
    {
      id: itemId,
      shoppingSessionId: sessionId,
      name: "Rice",
      quantity: "5.000",
      unit: "kg",
      notes: null,
      status: "pending",
      createdByUserId: "44444444-4444-4444-8444-444444444444",
      assignedToUserId: null,
      completedByUserId: null,
      createdAt: "2026-08-07T08:00:00Z",
      updatedAt: "2026-08-07T08:15:00Z",
      completedAt: null,
    },
  ],
  syncedAt,
};

type RepositoryHarness = Readonly<{
  repository: LocalGroceryCacheRepository;
  runAsync: jest.Mock;
  getFirstAsync: jest.Mock;
  getAllAsync: jest.Mock;
  transactionRunAsync: jest.Mock;
  withExclusiveTransactionAsync: jest.Mock;
}>;

function buildHarness(): RepositoryHarness {
  const runAsync = jest.fn().mockResolvedValue({ changes: 1, lastInsertRowId: 0 });
  const getFirstAsync = jest.fn().mockResolvedValue(null);
  const getAllAsync = jest.fn().mockResolvedValue([]);
  const transactionRunAsync = jest
    .fn()
    .mockResolvedValue({ changes: 1, lastInsertRowId: 0 });
  const withExclusiveTransactionAsync = jest.fn(
    async (
      task: (transaction: {
        execAsync(source: string): Promise<void>;
        runAsync(source: string, params: unknown): Promise<unknown>;
      }) => Promise<void>,
    ) => {
      await task({
        execAsync: jest.fn().mockResolvedValue(undefined),
        runAsync: transactionRunAsync,
      });
    },
  );
  const database: LocalDatabaseConnection = {
    execAsync: jest.fn().mockResolvedValue(undefined),
    runAsync,
    getFirstAsync,
    getAllAsync,
    withExclusiveTransactionAsync,
  };

  return {
    repository: new LocalGroceryCacheRepository(database),
    runAsync,
    getFirstAsync,
    getAllAsync,
    transactionRunAsync,
    withExclusiveTransactionAsync,
  };
}

describe("LocalGroceryCacheRepository", () => {
  it("replaces a complete session snapshot in one transaction", async () => {
    const harness = buildHarness();

    await harness.repository.replaceSessionSnapshot(snapshot);

    expect(harness.withExclusiveTransactionAsync).toHaveBeenCalledTimes(1);
    expect(harness.transactionRunAsync).toHaveBeenCalledTimes(3);
    expect(harness.transactionRunAsync.mock.calls[0][0]).toContain(
      "INSERT INTO cached_shopping_sessions",
    );
    expect(harness.transactionRunAsync.mock.calls[1][0]).toContain(
      "DELETE FROM cached_grocery_items",
    );
    expect(harness.transactionRunAsync.mock.calls[2][0]).toContain(
      "INSERT INTO cached_grocery_items",
    );
    expect(harness.transactionRunAsync.mock.calls[2][1]).toMatchObject({
      $householdId: householdId,
      $quantity: "5.000",
      $syncedAt: syncedAt,
    });
  });

  it("rejects an item from another session before changing the database", async () => {
    const harness = buildHarness();
    const invalidSnapshot = {
      ...snapshot,
      items: [{ ...snapshot.items[0], shoppingSessionId: "different-session" }],
    };

    await expect(
      harness.repository.replaceSessionSnapshot(invalidSnapshot),
    ).rejects.toThrow("must belong to the snapshot session");
    expect(harness.withExclusiveTransactionAsync).not.toHaveBeenCalled();
  });

  it("returns household-scoped cached items in application shape", async () => {
    const harness = buildHarness();
    harness.getAllAsync.mockResolvedValueOnce([itemRow]);

    await expect(harness.repository.listItems(householdId, sessionId)).resolves.toEqual(
      [expectedItem],
    );

    expect(harness.getAllAsync.mock.calls[0][0]).toContain(
      "household_id = $householdId",
    );
    expect(harness.getAllAsync.mock.calls[0][0]).toContain(
      "shopping_session_id = $shoppingSessionId",
    );
    expect(harness.getAllAsync.mock.calls[0][1]).toEqual({
      $householdId: householdId,
      $shoppingSessionId: sessionId,
    });
  });

  it("returns one scoped item and preserves its decimal quantity", async () => {
    const harness = buildHarness();
    harness.getFirstAsync.mockResolvedValueOnce(itemRow);

    await expect(
      harness.repository.getItem(householdId, sessionId, itemId),
    ).resolves.toEqual(expectedItem);

    expect(harness.getFirstAsync.mock.calls[0][1]).toEqual({
      $itemId: itemId,
      $householdId: householdId,
      $shoppingSessionId: sessionId,
    });
  });

  it("returns null when a scoped item is not cached", async () => {
    const harness = buildHarness();

    await expect(
      harness.repository.getItem(householdId, sessionId, itemId),
    ).resolves.toBeNull();
  });

  it("removes only the selected household session", async () => {
    const harness = buildHarness();

    await harness.repository.removeSession(householdId, sessionId);

    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "DELETE FROM cached_shopping_sessions",
    );
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $shoppingSessionId: sessionId,
      $householdId: householdId,
    });
  });

  it("clears household cache without deleting pending mutations", async () => {
    const harness = buildHarness();

    await harness.repository.clearHousehold(householdId);

    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "DELETE FROM cached_shopping_sessions",
    );
    expect(harness.runAsync.mock.calls[0][0]).not.toContain(
      "pending_grocery_mutations",
    );
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $householdId: householdId,
    });
  });

  it("propagates transaction failures without starting another write", async () => {
    const harness = buildHarness();
    const storageError = new Error("storage unavailable");
    harness.withExclusiveTransactionAsync.mockRejectedValueOnce(storageError);

    await expect(harness.repository.replaceSessionSnapshot(snapshot)).rejects.toBe(
      storageError,
    );
    expect(harness.withExclusiveTransactionAsync).toHaveBeenCalledTimes(1);
  });
});
