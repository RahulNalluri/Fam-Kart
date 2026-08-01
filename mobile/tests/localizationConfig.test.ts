import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  isSupportedLanguage,
  normalizeSupportedLanguage,
  resolveSupportedLanguage,
} from "../src/locales/config";
import { changeAppLanguage, createAppI18n } from "../src/locales/i18n";

describe("localization configuration", () => {
  it("supports English and Telugu", () => {
    expect(SUPPORTED_LANGUAGES).toEqual(["en", "te"]);
    expect(isSupportedLanguage("en")).toBe(true);
    expect(isSupportedLanguage("TE")).toBe(false);
    expect(isSupportedLanguage("hi")).toBe(false);
    expect(normalizeSupportedLanguage("TE")).toBe("te");
    expect(normalizeSupportedLanguage("hi")).toBeNull();
  });

  it("uses the first supported device language", () => {
    expect(
      resolveSupportedLanguage([
        { languageCode: "hi" },
        { languageCode: "te" },
        { languageCode: "en" },
      ]),
    ).toBe("te");
  });

  it("falls back to English for missing or unsupported languages", () => {
    expect(resolveSupportedLanguage([])).toBe(DEFAULT_LANGUAGE);
    expect(resolveSupportedLanguage([{ languageCode: null }])).toBe("en");
    expect(resolveSupportedLanguage([{ languageCode: "fr" }])).toBe("en");
  });

  it("creates initialized English and Telugu i18next instances", () => {
    const english = createAppI18n("en");
    const telugu = createAppI18n("te");

    expect(english.isInitialized).toBe(true);
    expect(english.language).toBe("en");
    expect(english.options.fallbackLng).toEqual(["en"]);
    expect(english.options.supportedLngs).toEqual(["en", "te", "cimode"]);
    expect(telugu.isInitialized).toBe(true);
    expect(telugu.language).toBe("te");
  });

  it("canonicalizes an external language value before changing i18next", async () => {
    const instance = createAppI18n("en");

    await expect(changeAppLanguage("TE", instance)).resolves.toBe(true);

    expect(instance.language).toBe("te");
  });
});
