import {
  createInstallationIdStore,
  InstallationIdStorage,
} from "../src/features/notifications/installationId";

jest.mock("expo-crypto", () => ({ randomUUID: jest.fn() }));
jest.mock("expo-secure-store", () => ({}));

const installationId = "11111111-1111-4111-8111-111111111111";

function storageWith(value: string | null): jest.Mocked<InstallationIdStorage> {
  return {
    getItemAsync: jest.fn().mockResolvedValue(value),
    setItemAsync: jest.fn().mockResolvedValue(undefined),
  };
}

describe("notification installation ID", () => {
  it("returns a valid stored installation ID", async () => {
    const storage = storageWith(installationId);
    const store = createInstallationIdStore({ storage });

    await expect(store.getExisting()).resolves.toBe(installationId);
    await expect(store.getOrCreate()).resolves.toBe(installationId);
    expect(storage.setItemAsync).not.toHaveBeenCalled();
  });

  it.each([null, "", "not-a-uuid"])(
    "creates and securely stores an ID when stored value is %s",
    async (stored) => {
      const storage = storageWith(stored);
      const createId = jest.fn(() => installationId);
      const store = createInstallationIdStore({ storage, createId });

      await expect(store.getOrCreate()).resolves.toBe(installationId);
      expect(storage.setItemAsync).toHaveBeenCalledWith(
        "familykart.notification.installation-id",
        installationId,
      );
    },
  );

  it("deduplicates concurrent creation", async () => {
    const storage = storageWith(null);
    const createId = jest.fn(() => installationId);
    const store = createInstallationIdStore({ storage, createId });

    await expect(
      Promise.all([store.getOrCreate(), store.getOrCreate()]),
    ).resolves.toEqual([installationId, installationId]);
    expect(createId).toHaveBeenCalledTimes(1);
    expect(storage.setItemAsync).toHaveBeenCalledTimes(1);
  });

  it("rejects an invalid generated identifier", async () => {
    const storage = storageWith(null);
    const store = createInstallationIdStore({
      storage,
      createId: () => "invalid",
    });

    await expect(store.getOrCreate()).rejects.toThrow();
    expect(storage.setItemAsync).not.toHaveBeenCalled();
  });
});
