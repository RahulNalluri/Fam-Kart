import { getLocales, Locale } from "expo-localization";

export const SUPPORTED_LANGUAGES = ["en", "te"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

type LanguageLocale = Pick<Locale, "languageCode">;

export function isSupportedLanguage(
  language: string | null | undefined,
): language is SupportedLanguage {
  return SUPPORTED_LANGUAGES.some(
    (supportedLanguage) => supportedLanguage === language?.toLowerCase(),
  );
}

export function resolveSupportedLanguage(
  locales: readonly LanguageLocale[] = getLocales(),
): SupportedLanguage {
  for (const locale of locales) {
    const languageCode = locale.languageCode?.toLowerCase();
    if (isSupportedLanguage(languageCode)) {
      return languageCode;
    }
  }

  return DEFAULT_LANGUAGE;
}
