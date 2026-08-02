import { i18n } from "i18next";
import { useTranslation } from "react-i18next";

import {
  DEFAULT_LANGUAGE,
  SupportedLanguage,
  normalizeSupportedLanguage,
} from "../locales/config";

export type RegistrationLanguageSource = Pick<i18n, "language" | "resolvedLanguage">;

export function resolveRegistrationLanguage(
  instance: RegistrationLanguageSource,
): SupportedLanguage {
  return (
    normalizeSupportedLanguage(instance.resolvedLanguage) ??
    normalizeSupportedLanguage(instance.language) ??
    DEFAULT_LANGUAGE
  );
}

export function useRegistrationLanguage(): SupportedLanguage {
  const { i18n: instance } = useTranslation();
  return resolveRegistrationLanguage(instance);
}
