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

  it("returns English application text", () => {
    const i18n = createAppI18n("en");

    expect(i18n.t("common.appName")).toBe("FamilyKart AI");
    expect(i18n.t("home.backendStatus.connected")).toBe("Connected");
    expect(i18n.t("realtime.authenticationRequired")).toBe(
      "Your session has expired. Please sign in again.",
    );
    expect(i18n.t("voice.permission.title")).toBe("Microphone permission");
    expect(i18n.t("voice.recorder.ready")).toBe("Recording ready");
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
  });

  it("falls back to English for an unsupported language", async () => {
    const i18n = createAppI18n("en");

    await i18n.changeLanguage("fr");

    expect(i18n.t("home.backendStatus.label")).toBe("Backend status");
  });
});
