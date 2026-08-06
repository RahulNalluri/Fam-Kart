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
  const withExclusiveTransactionAsync = jest.fn(
    async (
      task: (transaction: {
        execAsync(source: string): Promise<void>;
      }) => Promise<void>,
    ) => {
      await task({ execAsync: transactionExecAsync });
    },
  );
  const database: LocalDatabaseConnection = {
    execAsync,
    getFirstAsync: jest
      .fn()
      .mockResolvedValue(
        currentVersion === null ? null : { user_version: currentVersion },
      ),
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
  it.each([null, 0])("creates the first schema from version %s", async (version) => {
    const harness = buildDatabase(version);

    await initializeLocalDatabase(harness.database);

    expect(harness.execAsync).toHaveBeenCalledWith(
      "PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;",
    );
    expect(harness.withExclusiveTransactionAsync).toHaveBeenCalledTimes(1);
    expect(harness.transactionExecAsync).toHaveBeenCalledWith(
      expect.stringContaining("CREATE TABLE IF NOT EXISTS local_database_metadata"),
    );
    expect(harness.transactionExecAsync).toHaveBeenCalledWith(
      expect.stringContaining(`PRAGMA user_version = ${LOCAL_DATABASE_VERSION}`),
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
