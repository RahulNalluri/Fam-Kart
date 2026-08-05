import { englishTranslations } from "../src/locales/en";
import { createAppI18n } from "../src/locales/i18n";
import { teluguTranslations } from "../src/locales/te";

function collectTranslationKeys(value: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === "string"
      ? [path]
      : collectTranslationKeys(child as Record<string, unknown>, path);
  });
}

function collectTranslationValues(value: Record<string, unknown>): string[] {
  return Object.values(value).flatMap((child) =>
    typeof child === "string"
      ? [child]
      : collectTranslationValues(child as Record<string, unknown>),
  );
}

function collectTranslationEntries(
  value: Record<string, unknown>,
  prefix = "",
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, child]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return typeof child === "string"
        ? [[path, child]]
        : Object.entries(
            collectTranslationEntries(child as Record<string, unknown>, path),
          );
    }),
  );
}

function interpolationVariables(value: string): string[] {
  return [...value.matchAll(/{{\s*([^},\s]+)[^}]*}}/g)].map((match) => match[1]).sort();
}

describe("translation resources", () => {
  it("provides matching English and Telugu translation keys", () => {
    expect(collectTranslationKeys(teluguTranslations).sort()).toEqual(
      collectTranslationKeys(englishTranslations).sort(),
    );
  });

  it.each([
    ["English", englishTranslations],
    ["Telugu", teluguTranslations],
  ])("does not contain blank %s translations", (_language, translations) => {
    expect(collectTranslationValues(translations).every((value) => value.trim())).toBe(
      true,
    );
  });

  it("uses matching interpolation variables in English and Telugu", () => {
    const englishEntries = collectTranslationEntries(englishTranslations);
    const teluguEntries = collectTranslationEntries(teluguTranslations);

    for (const [key, englishValue] of Object.entries(englishEntries)) {
      expect(interpolationVariables(teluguEntries[key])).toEqual(
        interpolationVariables(englishValue),
      );
    }
  });

  it.each([
    ["English", englishTranslations],
    ["Telugu", teluguTranslations],
  ])("provides one and other forms for every %s plural", (_language, translations) => {
    const keys = collectTranslationKeys(translations);
    const keySet = new Set(keys);

    for (const key of keys.filter((candidate) => candidate.endsWith("_one"))) {
      expect(keySet.has(key.replace(/_one$/, "_other"))).toBe(true);
    }
  });

  it("returns English application text", () => {
    const i18n = createAppI18n("en");

    expect(i18n.t("common.appName")).toBe("FamilyKart AI");
    expect(i18n.t("home.backendStatus.connected")).toBe("Connected");
    expect(i18n.t("realtime.authenticationRequired")).toBe(
      "Your session has expired. Please sign in again.",
    );
    expect(i18n.t("voice.permission.title")).toBe("Microphone permission");
    expect(i18n.t("voice.recorder.ready")).toBe("Recording ready");
    expect(i18n.t("voice.confirmation.title")).toBe("Review voice items");
  });

  it("returns Telugu application text", () => {
    const i18n = createAppI18n("te");

    expect(i18n.t("home.description")).toBe(
      "ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం.",
    );
    expect(i18n.t("home.backendStatus.unavailable")).toBe("అందుబాటులో లేదు");
    expect(i18n.t("realtime.connectionInterrupted")).toBe(
      "తక్షణ కనెక్షన్‌కు అంతరాయం ఏర్పడింది. మళ్లీ కనెక్ట్ అవుతోంది.",
    );
    expect(i18n.t("voice.permission.title")).toBe("మైక్రోఫోన్ అనుమతి");
    expect(i18n.t("voice.recorder.ready")).toBe("రికార్డింగ్ సిద్ధంగా ఉంది");
    expect(i18n.t("voice.confirmation.title")).toBe("వాయిస్ సరుకులను తనిఖీ చేయండి");
  });

  it("falls back to English for an unsupported language", async () => {
    const i18n = createAppI18n("en");

    await i18n.changeLanguage("fr");

    expect(i18n.t("home.backendStatus.label")).toBe("Backend status");
  });
});
