import { z } from "zod";

import { SUPPORTED_LANGUAGES } from "../../locales/config";
import api from "../../services/api";

const normalizedEmailSchema = z.string().trim().toLowerCase().pipe(z.email());
const normalizedDisplayNameSchema = z
  .string()
  .transform((value) => value.trim())
  .pipe(z.string().min(1).max(120));

export const registrationInputSchema = z.strictObject({
  email: normalizedEmailSchema,
  displayName: normalizedDisplayNameSchema,
  password: z.string().min(8).max(128),
  preferredLanguage: z.enum(SUPPORTED_LANGUAGES),
});

const registeredUserApiSchema = z
  .strictObject({
    id: z.uuid(),
    email: z.email(),
    display_name: z.string().min(1).max(120),
    preferred_language: z.enum(SUPPORTED_LANGUAGES),
    is_active: z.boolean(),
    created_at: z.iso.datetime({ offset: true }),
  })
  .transform((value) => ({
    id: value.id,
    email: value.email,
    displayName: value.display_name,
    preferredLanguage: value.preferred_language,
    isActive: value.is_active,
    createdAt: value.created_at,
  }));

export type RegistrationInput = z.infer<typeof registrationInputSchema>;
export type RegisteredUser = z.infer<typeof registeredUserApiSchema>;

export async function registerAccount(
  input: RegistrationInput,
): Promise<RegisteredUser> {
  const data = registrationInputSchema.parse(input);
  const response = await api.post<unknown>("/api/v1/auth/register", {
    email: data.email,
    display_name: data.displayName,
    password: data.password,
    preferred_language: data.preferredLanguage,
  });
  return registeredUserApiSchema.parse(response.data);
}
