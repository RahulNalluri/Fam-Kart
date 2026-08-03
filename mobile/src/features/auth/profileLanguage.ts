import { i18n } from "i18next";
import { z } from "zod";

import { SUPPORTED_LANGUAGES } from "../../locales/config";
import { appI18n, changeAppLanguage } from "../../locales/i18n";
import {
  LanguageStorage,
  saveSelectedLanguage,
  secureLanguageStorage,
} from "../../locales/languageStorage";
import api from "../../services/api";
import { UserProfile, userProfileApiSchema } from "./registration";

const profileLanguageUpdateSchema = z.strictObject({
  accessToken: z.string().trim().min(1),
  preferredLanguage: z.enum(SUPPORTED_LANGUAGES),
});

export type ProfileLanguageUpdate = z.infer<typeof profileLanguageUpdateSchema>;

export type ProfileLanguageUpdateDependencies = {
  instance?: i18n;
  storage?: LanguageStorage;
};

export async function updateProfileLanguage(
  update: ProfileLanguageUpdate,
  {
    instance = appI18n,
    storage = secureLanguageStorage,
  }: ProfileLanguageUpdateDependencies = {},
): Promise<UserProfile> {
  const validated = profileLanguageUpdateSchema.parse(update);
  const response = await api.patch<unknown>(
    "/api/v1/users/me",
    { preferred_language: validated.preferredLanguage },
    {
      headers: { Authorization: `Bearer ${validated.accessToken}` },
    },
  );
  const profile = userProfileApiSchema.parse(response.data);

  await saveSelectedLanguage(profile.preferredLanguage, storage);
  await changeAppLanguage(profile.preferredLanguage, instance);
  return profile;
}
