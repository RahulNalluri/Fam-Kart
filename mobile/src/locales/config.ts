import { getLocales, Locale } from "expo-localization";

export const SUPPORTED_LANGUAGES = ["en", "te"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

type LanguageLocale = Pick<Locale, "languageCode">;

export function isSupportedLanguage(
  language: string | null | undefined,
): language is SupportedLanguage {
  return SUPPORTED_LANGUAGES.some(
    (supportedLanguage) => supportedLanguage === language,
  );
}

export function normalizeSupportedLanguage(
  language: string | null | undefined,
): SupportedLanguage | null {
  const normalizedLanguage = language?.toLowerCase();
  return (
    SUPPORTED_LANGUAGES.find(
      (supportedLanguage) => supportedLanguage === normalizedLanguage,
    ) ?? null
  );
}

export function resolveSupportedLanguage(
  locales: readonly LanguageLocale[] = getLocales(),
): SupportedLanguage {
  for (const locale of locales) {
    const language = normalizeSupportedLanguage(locale.languageCode);
    if (language) {
      return language;
    }
  }

  return DEFAULT_LANGUAGE;
}
