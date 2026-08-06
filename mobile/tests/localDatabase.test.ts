import {
  initializeLocalDatabase,
  LOCAL_DATABASE_NAME,
  LOCAL_DATABASE_VERSION,
  LocalDatabaseConnection,
  openLocalDatabase,
} from "../src/features/offline/localDatabase";

type DatabaseHarness = Readonly<{
  database: LocalDatabaseConnection;
  execAsync: jest.Mock<Promise<void>, [string]>;
  transactionExecAsync: jest.Mock<Promise<void>, [string]>;
  withExclusiveTransactionAsync: jest.Mock;
}>;

function buildDatabase(currentVersion: number | null): DatabaseHarness {
  const execAsync = jest.fn<Promise<void>, [string]>().mockResolvedValue(undefined);
  const transactionExecAsync = jest
    .fn<Promise<void>, [string]>()
    .mockResolvedValue(undefined);
  const runAsync = jest.fn().mockResolvedValue({ changes: 0, lastInsertRowId: 0 });
  const transactionRunAsync = jest
    .fn()
    .mockResolvedValue({ changes: 0, lastInsertRowId: 0 });
  const withExclusiveTransactionAsync = jest.fn(
    async (
      task: (transaction: {
        execAsync(source: string): Promise<void>;
        runAsync(source: string, params: unknown): Promise<unknown>;
      }) => Promise<void>,
    ) => {
      await task({
        execAsync: transactionExecAsync,
        runAsync: transactionRunAsync,
      });
    },
  );
  const database: LocalDatabaseConnection = {
    execAsync,
    runAsync,
    getFirstAsync: jest
      .fn()
      .mockResolvedValue(
        currentVersion === null ? null : { user_version: currentVersion },
      ),
    getAllAsync: jest.fn().mockResolvedValue([]),
    withExclusiveTransactionAsync,
  };

  return {
    database,
    execAsync,
    transactionExecAsync,
    withExclusiveTransactionAsync,
  };
}

describe("Expo SQLite foundation", () => {
  it.each([null, 0])("migrates a new database from version %s", async (version) => {
    const harness = buildDatabase(version);

    await initializeLocalDatabase(harness.database);

    expect(harness.execAsync).toHaveBeenCalledWith(
      "PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;",
    );
    expect(harness.withExclusiveTransactionAsync).toHaveBeenCalledTimes(1);
    expect(harness.transactionExecAsync.mock.calls).toEqual([
      [expect.stringContaining("CREATE TABLE local_database_metadata")],
      ["PRAGMA user_version = 1;"],
      [expect.stringContaining("CREATE TABLE cached_grocery_items")],
      [`PRAGMA user_version = ${LOCAL_DATABASE_VERSION};`],
    ]);
  });

  it("upgrades an existing foundation database without rerunning version 1", async () => {
    const harness = buildDatabase(1);

    await initializeLocalDatabase(harness.database);

    expect(harness.transactionExecAsync.mock.calls).toEqual([
      [expect.stringContaining("CREATE TABLE cached_shopping_sessions")],
      [`PRAGMA user_version = ${LOCAL_DATABASE_VERSION};`],
    ]);
    expect(harness.transactionExecAsync).not.toHaveBeenCalledWith(
      expect.stringContaining("CREATE TABLE local_database_metadata"),
    );
  });

  it("does not rerun migrations for an initialized database", async () => {
    const harness = buildDatabase(LOCAL_DATABASE_VERSION);

    await initializeLocalDatabase(harness.database);

    expect(harness.withExclusiveTransactionAsync).not.toHaveBeenCalled();
  });

  it("rejects a database created by a newer app version", async () => {
    const harness = buildDatabase(LOCAL_DATABASE_VERSION + 1);

    await expect(initializeLocalDatabase(harness.database)).rejects.toThrow(
      "is newer than this app supports",
    );
    expect(harness.withExclusiveTransactionAsync).not.toHaveBeenCalled();
  });

  it.each([-1, 1.5])("rejects invalid schema version %s", async (version) => {
    const harness = buildDatabase(version);

    await expect(initializeLocalDatabase(harness.database)).rejects.toThrow(
      "invalid schema version",
    );
  });

  it("opens the named database and initializes it", async () => {
    const harness = buildDatabase(LOCAL_DATABASE_VERSION);
    const openDatabase = jest.fn().mockResolvedValue(harness.database);

    await expect(openLocalDatabase(openDatabase)).resolves.toBe(harness.database);

    expect(openDatabase).toHaveBeenCalledWith(LOCAL_DATABASE_NAME);
    expect(harness.execAsync).toHaveBeenCalledTimes(1);
  });

  it("propagates migration failures without reporting initialization success", async () => {
    const harness = buildDatabase(0);
    const migrationError = new Error("migration failed");
    harness.withExclusiveTransactionAsync.mockRejectedValueOnce(migrationError);

    await expect(initializeLocalDatabase(harness.database)).rejects.toBe(
      migrationError,
    );
  });
});
