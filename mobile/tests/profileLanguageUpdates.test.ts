import { AxiosResponse } from "axios";

import { updateProfileLanguage } from "../src/features/auth/profileLanguage";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";
import {
  LanguageStorage,
  SELECTED_LANGUAGE_STORAGE_KEY,
} from "../src/locales/languageStorage";
import api from "../src/services/api";

jest.mock("../src/services/api", () => ({
  __esModule: true,
  default: {
    patch: jest.fn(),
  },
}));

const userId = "11111111-1111-4111-8111-111111111111";
const accessToken = "profile-language-access-token";
const patchMock = api.patch as jest.MockedFunction<typeof api.patch>;

function profileResponse(preferredLanguage: string) {
  return {
    id: userId,
    email: "rahul@example.com",
    display_name: "Rahul",
    preferred_language: preferredLanguage,
    is_active: true,
    created_at: "2026-08-03T08:00:00Z",
  };
}

function responseWith(data: unknown): AxiosResponse<unknown> {
  return {
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: { headers: {} } as AxiosResponse["config"],
  };
}

function createStorage(): jest.Mocked<LanguageStorage> {
  return {
    getItemAsync: jest.fn().mockResolvedValue(null),
    setItemAsync: jest.fn().mockResolvedValue(undefined),
  };
}

describe("profile language updates", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it.each<[SupportedLanguage, SupportedLanguage]>([
    ["en", "te"],
    ["te", "en"],
  ])(
    "updates the account language from %s to %s and synchronizes mobile state",
    async (initialLanguage, preferredLanguage) => {
      const instance = createAppI18n(initialLanguage);
      const storage = createStorage();
      patchMock.mockResolvedValue(responseWith(profileResponse(preferredLanguage)));

      const profile = await updateProfileLanguage(
        { accessToken, preferredLanguage },
        { instance, storage },
      );

      expect(patchMock).toHaveBeenCalledWith(
        "/api/v1/users/me",
        { preferred_language: preferredLanguage },
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      expect(storage.setItemAsync).toHaveBeenCalledWith(
        SELECTED_LANGUAGE_STORAGE_KEY,
        preferredLanguage,
      );
      expect(instance.language).toBe(preferredLanguage);
      expect(profile.preferredLanguage).toBe(preferredLanguage);
    },
  );

  it.each([
    { accessToken: "   ", preferredLanguage: "te" },
    { accessToken, preferredLanguage: "fr" },
  ])("rejects invalid update data before calling the backend", async (update) => {
    const instance = createAppI18n("en");
    const storage = createStorage();

    await expect(
      updateProfileLanguage(update as never, { instance, storage }),
    ).rejects.toBeDefined();

    expect(patchMock).not.toHaveBeenCalled();
    expect(storage.setItemAsync).not.toHaveBeenCalled();
    expect(instance.language).toBe("en");
  });

  it("does not change local language when the backend rejects the update", async () => {
    const instance = createAppI18n("en");
    const storage = createStorage();
    const backendError = new Error("Please log in again to continue.");
    patchMock.mockRejectedValue(backendError);

    await expect(
      updateProfileLanguage(
        { accessToken, preferredLanguage: "te" },
        { instance, storage },
      ),
    ).rejects.toBe(backendError);

    expect(storage.setItemAsync).not.toHaveBeenCalled();
    expect(instance.language).toBe("en");
  });

  it("rejects malformed profile data before changing local language", async () => {
    const instance = createAppI18n("en");
    const storage = createStorage();
    patchMock.mockResolvedValue(responseWith(profileResponse("fr")));

    await expect(
      updateProfileLanguage(
        { accessToken, preferredLanguage: "te" },
        { instance, storage },
      ),
    ).rejects.toBeDefined();

    expect(storage.setItemAsync).not.toHaveBeenCalled();
    expect(instance.language).toBe("en");
  });

  it("does not switch the visible language when local persistence fails", async () => {
    const instance = createAppI18n("en");
    const storage = createStorage();
    const storageError = new Error("SecureStore unavailable");
    storage.setItemAsync.mockRejectedValue(storageError);
    patchMock.mockResolvedValue(responseWith(profileResponse("te")));

    await expect(
      updateProfileLanguage(
        { accessToken, preferredLanguage: "te" },
        { instance, storage },
      ),
    ).rejects.toBe(storageError);

    expect(instance.language).toBe("en");
  });
});
