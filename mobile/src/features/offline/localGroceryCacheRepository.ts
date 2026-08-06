import { LocalDatabaseConnection } from "./localDatabase";

export type CachedShoppingSession = Readonly<{
  id: string;
  householdId: string;
  createdByUserId: string | null;
  status: "active" | "completed";
  createdAt: string;
  completedAt: string | null;
}>;

export type CachedGroceryItem = Readonly<{
  id: string;
  householdId: string;
  shoppingSessionId: string;
  name: string;
  quantity: string | null;
  unit: string | null;
  notes: string | null;
  status: "pending" | "completed";
  createdByUserId: string | null;
  assignedToUserId: string | null;
  completedByUserId: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  syncedAt: string;
}>;

export type GrocerySessionSnapshot = Readonly<{
  session: CachedShoppingSession;
  items: readonly Omit<CachedGroceryItem, "householdId" | "syncedAt">[];
  syncedAt: string;
}>;

type CachedGroceryItemRow = Readonly<{
  id: string;
  household_id: string;
  shopping_session_id: string;
  name: string;
  quantity: string | null;
  unit: string | null;
  notes: string | null;
  status: "pending" | "completed";
  created_by_user_id: string | null;
  assigned_to_user_id: string | null;
  completed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  synced_at: string;
}>;

const UPSERT_SESSION_SQL = `
  INSERT INTO cached_shopping_sessions (
    id, household_id, created_by_user_id, status, created_at, completed_at, synced_at
  ) VALUES (
    $id, $householdId, $createdByUserId, $status, $createdAt, $completedAt, $syncedAt
  )
  ON CONFLICT(id) DO UPDATE SET
    household_id = excluded.household_id,
    created_by_user_id = excluded.created_by_user_id,
    status = excluded.status,
    created_at = excluded.created_at,
    completed_at = excluded.completed_at,
    synced_at = excluded.synced_at;
`;

const INSERT_ITEM_SQL = `
  INSERT INTO cached_grocery_items (
    id, household_id, shopping_session_id, name, quantity, unit, notes, status,
    created_by_user_id, assigned_to_user_id, completed_by_user_id,
    created_at, updated_at, completed_at, synced_at
  ) VALUES (
    $id, $householdId, $shoppingSessionId, $name, $quantity, $unit, $notes, $status,
    $createdByUserId, $assignedToUserId, $completedByUserId,
    $createdAt, $updatedAt, $completedAt, $syncedAt
  );
`;

const SELECT_ITEM_COLUMNS = `
  id, household_id, shopping_session_id, name, quantity, unit, notes, status,
  created_by_user_id, assigned_to_user_id, completed_by_user_id,
  created_at, updated_at, completed_at, synced_at
`;

function mapGroceryItem(row: CachedGroceryItemRow): CachedGroceryItem {
  return {
    id: row.id,
    householdId: row.household_id,
    shoppingSessionId: row.shopping_session_id,
    name: row.name,
    quantity: row.quantity,
    unit: row.unit,
    notes: row.notes,
    status: row.status,
    createdByUserId: row.created_by_user_id,
    assignedToUserId: row.assigned_to_user_id,
    completedByUserId: row.completed_by_user_id,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    completedAt: row.completed_at,
    syncedAt: row.synced_at,
  };
}

export class LocalGroceryCacheRepository {
  constructor(private readonly database: LocalDatabaseConnection) {}

  async replaceSessionSnapshot(snapshot: GrocerySessionSnapshot): Promise<void> {
    const { session, items, syncedAt } = snapshot;
    if (items.some((item) => item.shoppingSessionId !== session.id)) {
      throw new Error("Every cached grocery item must belong to the snapshot session.");
    }

    await this.database.withExclusiveTransactionAsync(async (transaction) => {
      await transaction.runAsync(UPSERT_SESSION_SQL, {
        $id: session.id,
        $householdId: session.householdId,
        $createdByUserId: session.createdByUserId,
        $status: session.status,
        $createdAt: session.createdAt,
        $completedAt: session.completedAt,
        $syncedAt: syncedAt,
      });
      await transaction.runAsync(
        `DELETE FROM cached_grocery_items
         WHERE household_id = $householdId AND shopping_session_id = $sessionId;`,
        { $householdId: session.householdId, $sessionId: session.id },
      );

      for (const item of items) {
        await transaction.runAsync(INSERT_ITEM_SQL, {
          $id: item.id,
          $householdId: session.householdId,
          $shoppingSessionId: item.shoppingSessionId,
          $name: item.name,
          $quantity: item.quantity,
          $unit: item.unit,
          $notes: item.notes,
          $status: item.status,
          $createdByUserId: item.createdByUserId,
          $assignedToUserId: item.assignedToUserId,
          $completedByUserId: item.completedByUserId,
          $createdAt: item.createdAt,
          $updatedAt: item.updatedAt,
          $completedAt: item.completedAt,
          $syncedAt: syncedAt,
        });
      }
    });
  }

  async listItems(
    householdId: string,
    shoppingSessionId: string,
  ): Promise<CachedGroceryItem[]> {
    const rows = await this.database.getAllAsync<CachedGroceryItemRow>(
      `SELECT ${SELECT_ITEM_COLUMNS}
       FROM cached_grocery_items
       WHERE household_id = $householdId
         AND shopping_session_id = $shoppingSessionId
       ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at ASC, id ASC;`,
      { $householdId: householdId, $shoppingSessionId: shoppingSessionId },
    );
    return rows.map(mapGroceryItem);
  }

  async getItem(
    householdId: string,
    shoppingSessionId: string,
    itemId: string,
  ): Promise<CachedGroceryItem | null> {
    const row = await this.database.getFirstAsync<CachedGroceryItemRow>(
      `SELECT ${SELECT_ITEM_COLUMNS}
       FROM cached_grocery_items
       WHERE id = $itemId
         AND household_id = $householdId
         AND shopping_session_id = $shoppingSessionId;`,
      {
        $itemId: itemId,
        $householdId: householdId,
        $shoppingSessionId: shoppingSessionId,
      },
    );
    return row === null ? null : mapGroceryItem(row);
  }

  async removeSession(householdId: string, shoppingSessionId: string): Promise<void> {
    await this.database.runAsync(
      `DELETE FROM cached_shopping_sessions
       WHERE id = $shoppingSessionId AND household_id = $householdId;`,
      { $shoppingSessionId: shoppingSessionId, $householdId: householdId },
    );
  }

  async clearHousehold(householdId: string): Promise<void> {
    await this.database.runAsync(
      "DELETE FROM cached_shopping_sessions WHERE household_id = $householdId;",
      { $householdId: householdId },
    );
  }
}
