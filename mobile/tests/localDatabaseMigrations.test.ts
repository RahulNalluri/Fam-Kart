import {
  CURRENT_LOCAL_DATABASE_VERSION,
  getPendingLocalDatabaseMigrations,
  LOCAL_DATABASE_MIGRATIONS,
} from "../src/features/offline/localDatabaseMigrations";

describe("local database migrations", () => {
  it("keeps migration versions sequential and reports the latest version", () => {
    expect(LOCAL_DATABASE_MIGRATIONS.map(({ version }) => version)).toEqual([1, 2]);
    expect(CURRENT_LOCAL_DATABASE_VERSION).toBe(2);
  });

  it("selects only migrations newer than the installed schema", () => {
    expect(getPendingLocalDatabaseMigrations(0).map(({ version }) => version)).toEqual([
      1, 2,
    ]);
    expect(getPendingLocalDatabaseMigrations(1).map(({ version }) => version)).toEqual([
      2,
    ]);
    expect(getPendingLocalDatabaseMigrations(2)).toEqual([]);
  });

  it("defines the server snapshot cache tables and lookup indexes", () => {
    const schema = LOCAL_DATABASE_MIGRATIONS[1].sql;

    expect(schema).toContain("CREATE TABLE cached_shopping_sessions");
    expect(schema).toContain("CREATE TABLE cached_grocery_items");
    expect(schema).toContain("FOREIGN KEY (shopping_session_id)");
    expect(schema).toContain("ON DELETE CASCADE");
    expect(schema).toContain("ix_cached_sessions_household_status");
    expect(schema).toContain("ix_cached_items_household_session_status");
  });

  it("defines a durable FIFO mutation queue with policy constraints", () => {
    const schema = LOCAL_DATABASE_MIGRATIONS[1].sql;

    expect(schema).toContain("CREATE TABLE pending_grocery_mutations");
    expect(schema).toContain("mutation_id TEXT PRIMARY KEY NOT NULL");
    expect(schema).toContain("CHECK (json_valid(payload_json))");
    expect(schema).toContain("CHECK (attempt_count >= 0)");
    expect(schema).toContain("'requires_review'");
    expect(schema).toContain("(household_id, status, created_at, mutation_id)");
  });

  it("does not tie queued work to disposable cache rows", () => {
    const queueSchema = LOCAL_DATABASE_MIGRATIONS[1].sql.split(
      "CREATE TABLE pending_grocery_mutations",
    )[1];

    expect(queueSchema).toBeDefined();
    expect(queueSchema).not.toContain("FOREIGN KEY");
  });
});
