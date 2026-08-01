import { i18n } from "i18next";
import { useEffect } from "react";

import { isSupportedLanguage } from "../locales/config";
import { appI18n } from "../locales/i18n";

export async function applyLanguagePreference(
  preferredLanguage: string | null | undefined,
  instance: i18n = appI18n,
): Promise<boolean> {
  if (!isSupportedLanguage(preferredLanguage)) {
    return false;
  }

  const activeLanguage = instance.resolvedLanguage ?? instance.language;
  if (activeLanguage === preferredLanguage) {
    return false;
  }

  await instance.changeLanguage(preferredLanguage);
  return true;
}

export function useLanguagePreference(
  preferredLanguage: string | null | undefined,
  instance: i18n = appI18n,
): void {
  useEffect(() => {
    void applyLanguagePreference(preferredLanguage, instance).catch(() => undefined);
  }, [instance, preferredLanguage]);
}
