import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  isSupportedLanguage,
  resolveSupportedLanguage,
} from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";

describe("localization configuration", () => {
  it("supports English and Telugu", () => {
    expect(SUPPORTED_LANGUAGES).toEqual(["en", "te"]);
    expect(isSupportedLanguage("en")).toBe(true);
    expect(isSupportedLanguage("TE")).toBe(true);
    expect(isSupportedLanguage("hi")).toBe(false);
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
});
