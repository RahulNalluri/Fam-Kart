import { openDatabaseAsync } from "expo-sqlite";

export const LOCAL_DATABASE_NAME = "familykart.db";
export const LOCAL_DATABASE_VERSION = 1;

type LocalDatabaseTransaction = Readonly<{
  execAsync(source: string): Promise<void>;
}>;

export type LocalDatabaseConnection = Readonly<{
  execAsync(source: string): Promise<void>;
  getFirstAsync<T>(source: string): Promise<T | null>;
  withExclusiveTransactionAsync(
    task: (transaction: LocalDatabaseTransaction) => Promise<void>,
  ): Promise<void>;
}>;

type OpenDatabase = (databaseName: string) => Promise<LocalDatabaseConnection>;

type UserVersionRow = Readonly<{
  user_version: number;
}>;

const CREATE_FOUNDATION_SCHEMA = `
  CREATE TABLE IF NOT EXISTS local_database_metadata (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
  );
  PRAGMA user_version = ${LOCAL_DATABASE_VERSION};
`;

let localDatabasePromise: Promise<LocalDatabaseConnection> | null = null;

export async function initializeLocalDatabase(
  database: LocalDatabaseConnection,
): Promise<void> {
  await database.execAsync("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;");

  const row = await database.getFirstAsync<UserVersionRow>("PRAGMA user_version;");
  const currentVersion = row?.user_version ?? 0;

  if (!Number.isInteger(currentVersion) || currentVersion < 0) {
    throw new Error("The local database has an invalid schema version.");
  }
  if (currentVersion > LOCAL_DATABASE_VERSION) {
    throw new Error(
      `The local database schema version ${currentVersion} is newer than this app supports.`,
    );
  }
  if (currentVersion === LOCAL_DATABASE_VERSION) {
    return;
  }

  await database.withExclusiveTransactionAsync(async (transaction) => {
    await transaction.execAsync(CREATE_FOUNDATION_SCHEMA);
  });
}

export async function openLocalDatabase(
  openDatabase: OpenDatabase = openDatabaseAsync,
): Promise<LocalDatabaseConnection> {
  const database = await openDatabase(LOCAL_DATABASE_NAME);
  await initializeLocalDatabase(database);
  return database;
}

export function getLocalDatabase(): Promise<LocalDatabaseConnection> {
  if (localDatabasePromise === null) {
    localDatabasePromise = openLocalDatabase().catch((error: unknown) => {
      localDatabasePromise = null;
      throw error;
    });
  }
  return localDatabasePromise;
}
