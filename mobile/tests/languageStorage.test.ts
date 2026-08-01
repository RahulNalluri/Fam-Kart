import {
  LanguageStorage,
  SELECTED_LANGUAGE_STORAGE_KEY,
  loadSelectedLanguage,
  saveSelectedLanguage,
} from "../src/locales/languageStorage";

function createStorage(value: string | null): jest.Mocked<LanguageStorage> {
  return {
    getItemAsync: jest.fn().mockResolvedValue(value),
    setItemAsync: jest.fn().mockResolvedValue(undefined),
  };
}

describe("selected language storage", () => {
  it.each(["en", "te"])("loads the supported %s language", async (language) => {
    const storage = createStorage(language);

    await expect(loadSelectedLanguage(storage)).resolves.toBe(language);
    expect(storage.getItemAsync).toHaveBeenCalledWith(SELECTED_LANGUAGE_STORAGE_KEY);
  });

  it("normalizes a supported stored language", async () => {
    await expect(loadSelectedLanguage(createStorage("TE"))).resolves.toBe("te");
  });

  it.each([null, "fr", ""])(
    "ignores the unsupported stored value %s",
    async (value) => {
      await expect(loadSelectedLanguage(createStorage(value))).resolves.toBeNull();
    },
  );

  it("saves a supported language under the stable storage key", async () => {
    const storage = createStorage(null);

    await saveSelectedLanguage("te", storage);

    expect(storage.setItemAsync).toHaveBeenCalledWith(
      SELECTED_LANGUAGE_STORAGE_KEY,
      "te",
    );
  });
});
