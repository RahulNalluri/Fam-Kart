import { createInstance, i18n } from "i18next";
import { initReactI18next } from "react-i18next";

import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
  normalizeSupportedLanguage,
  resolveSupportedLanguage,
} from "./config";
import { translationResources } from "./resources";

export function createAppI18n(
  language: SupportedLanguage = resolveSupportedLanguage(),
): i18n {
  const instance = createInstance();
  void instance.use(initReactI18next).init({
    fallbackLng: DEFAULT_LANGUAGE,
    initAsync: false,
    interpolation: {
      escapeValue: false,
    },
    lng: language,
    resources: translationResources,
    supportedLngs: [...SUPPORTED_LANGUAGES],
  });
  return instance;
}

export const appI18n = createAppI18n();

export async function changeAppLanguage(
  language: string | null | undefined,
  instance: i18n = appI18n,
): Promise<boolean> {
  const normalizedLanguage = normalizeSupportedLanguage(language);
  if (!normalizedLanguage) {
    return false;
  }

  const activeLanguage = normalizeSupportedLanguage(
    instance.resolvedLanguage ?? instance.language,
  );
  if (activeLanguage === normalizedLanguage) {
    return false;
  }

  await instance.changeLanguage(normalizedLanguage);
  return true;
}
