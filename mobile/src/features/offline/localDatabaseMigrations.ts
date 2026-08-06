export type LocalDatabaseMigration = Readonly<{
  version: number;
  sql: string;
}>;

export const LOCAL_DATABASE_MIGRATIONS: readonly LocalDatabaseMigration[] = [
  {
    version: 1,
    sql: `
      CREATE TABLE local_database_metadata (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
      );
    `,
  },
  {
    version: 2,
    sql: `
      CREATE TABLE cached_shopping_sessions (
        id TEXT PRIMARY KEY NOT NULL,
        household_id TEXT NOT NULL,
        created_by_user_id TEXT,
        status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        synced_at TEXT NOT NULL
      );

      CREATE INDEX ix_cached_sessions_household_status
        ON cached_shopping_sessions (household_id, status);

      CREATE TABLE cached_grocery_items (
        id TEXT PRIMARY KEY NOT NULL,
        household_id TEXT NOT NULL,
        shopping_session_id TEXT NOT NULL,
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        quantity TEXT,
        unit TEXT,
        notes TEXT,
        status TEXT NOT NULL CHECK (status IN ('pending', 'completed')),
        created_by_user_id TEXT,
        assigned_to_user_id TEXT,
        completed_by_user_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        synced_at TEXT NOT NULL,
        FOREIGN KEY (shopping_session_id)
          REFERENCES cached_shopping_sessions (id) ON DELETE CASCADE
      );

      CREATE INDEX ix_cached_items_household_session_status
        ON cached_grocery_items (household_id, shopping_session_id, status);

      CREATE TABLE pending_grocery_mutations (
        mutation_id TEXT PRIMARY KEY NOT NULL,
        household_id TEXT NOT NULL,
        shopping_session_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        operation TEXT NOT NULL
          CHECK (operation IN ('add', 'edit', 'complete', 'reopen', 'delete')),
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        base_updated_at TEXT,
        created_at TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        status TEXT NOT NULL DEFAULT 'pending'
          CHECK (status IN ('pending', 'requires_review')),
        last_error_code TEXT
      );

      CREATE INDEX ix_pending_mutations_household_replay
        ON pending_grocery_mutations
          (household_id, status, created_at, mutation_id);

      CREATE INDEX ix_pending_mutations_item_status
        ON pending_grocery_mutations (item_id, status);
    `,
  },
];

export const CURRENT_LOCAL_DATABASE_VERSION =
  LOCAL_DATABASE_MIGRATIONS[LOCAL_DATABASE_MIGRATIONS.length - 1].version;

export function getPendingLocalDatabaseMigrations(
  currentVersion: number,
): readonly LocalDatabaseMigration[] {
  return LOCAL_DATABASE_MIGRATIONS.filter(
    (migration) => migration.version > currentVersion,
  );
}
