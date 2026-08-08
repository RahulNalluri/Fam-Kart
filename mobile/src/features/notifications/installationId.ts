import { randomUUID } from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { z } from "zod";

const INSTALLATION_ID_KEY = "familykart.notification.installation-id";
const installationIdSchema = z.uuid();

export interface InstallationIdStorage {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
}

export interface InstallationIdStore {
  getExisting(): Promise<string | null>;
  getOrCreate(): Promise<string>;
}

export type InstallationIdDependencies = {
  storage?: InstallationIdStorage;
  createId?: () => string;
};

export function createInstallationIdStore({
  storage = SecureStore,
  createId = randomUUID,
}: InstallationIdDependencies = {}): InstallationIdStore {
  let pendingId: Promise<string> | null = null;

  async function getExisting(): Promise<string | null> {
    const stored = await storage.getItemAsync(INSTALLATION_ID_KEY);
    const parsed = installationIdSchema.safeParse(stored);
    return parsed.success ? parsed.data : null;
  }

  async function createAndStore(): Promise<string> {
    const existing = await getExisting();
    if (existing !== null) {
      return existing;
    }

    const installationId = installationIdSchema.parse(createId());
    await storage.setItemAsync(INSTALLATION_ID_KEY, installationId);
    return installationId;
  }

  return {
    getExisting,
    async getOrCreate() {
      pendingId ??= createAndStore().finally(() => {
        pendingId = null;
      });
      return pendingId;
    },
  };
}

export const secureInstallationIdStore = createInstallationIdStore();
