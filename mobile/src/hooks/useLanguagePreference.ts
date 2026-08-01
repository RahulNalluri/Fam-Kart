import { i18n } from "i18next";
import { useEffect } from "react";

import { appI18n, changeAppLanguage } from "../locales/i18n";

export async function applyLanguagePreference(
  preferredLanguage: string | null | undefined,
  instance: i18n = appI18n,
): Promise<boolean> {
  return changeAppLanguage(preferredLanguage, instance);
}

export function useLanguagePreference(
  preferredLanguage: string | null | undefined,
  instance: i18n = appI18n,
): void {
  useEffect(() => {
    void applyLanguagePreference(preferredLanguage, instance).catch(() => undefined);
  }, [instance, preferredLanguage]);
}
