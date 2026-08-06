import { openDatabaseAsync } from "expo-sqlite";

import {
  CURRENT_LOCAL_DATABASE_VERSION,
  getPendingLocalDatabaseMigrations,
} from "./localDatabaseMigrations";

export const LOCAL_DATABASE_NAME = "familykart.db";
export const LOCAL_DATABASE_VERSION = CURRENT_LOCAL_DATABASE_VERSION;

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
    for (const migration of getPendingLocalDatabaseMigrations(currentVersion)) {
      await transaction.execAsync(migration.sql);
      await transaction.execAsync(`PRAGMA user_version = ${migration.version};`);
    }
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
