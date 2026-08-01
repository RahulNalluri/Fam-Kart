import * as SecureStore from "expo-secure-store";

import { SupportedLanguage, normalizeSupportedLanguage } from "./config";

export const SELECTED_LANGUAGE_STORAGE_KEY = "familykart.selected-language";

export type LanguageStorage = {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
};

export const secureLanguageStorage: LanguageStorage = SecureStore;

export async function loadSelectedLanguage(
  storage: LanguageStorage = secureLanguageStorage,
): Promise<SupportedLanguage | null> {
  const storedLanguage = await storage.getItemAsync(SELECTED_LANGUAGE_STORAGE_KEY);
  return normalizeSupportedLanguage(storedLanguage);
}

export async function saveSelectedLanguage(
  language: SupportedLanguage,
  storage: LanguageStorage = secureLanguageStorage,
): Promise<void> {
  await storage.setItemAsync(SELECTED_LANGUAGE_STORAGE_KEY, language);
}
