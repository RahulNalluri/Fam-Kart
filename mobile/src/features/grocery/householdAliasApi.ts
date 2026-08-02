import { AxiosRequestConfig } from "axios";
import { z } from "zod";

import api from "../../services/api";
import { GroceryItemKey, groceryDictionaryEntries } from "./dictionary";

const canonicalGroceryKeys = new Set<string>(
  groceryDictionaryEntries.map((entry) => entry.key),
);

const canonicalGroceryKeySchema = z
  .string()
  .refine((value) => canonicalGroceryKeys.has(value), {
    message: "Canonical grocery item is not supported.",
  })
  .transform((value) => value as GroceryItemKey);

const authenticatedHouseholdRequestSchema = z.strictObject({
  householdId: z.uuid(),
  accessToken: z.string().trim().min(1),
});

const aliasIdSchema = z.uuid();
const aliasTextSchema = z
  .string()
  .min(1)
  .max(160)
  .refine((value) => value.trim().length > 0, {
    message: "Household grocery alias cannot be blank.",
  });

export const createHouseholdGroceryAliasInputSchema = z.strictObject({
  alias: aliasTextSchema,
  canonicalKey: canonicalGroceryKeySchema,
});

export const updateHouseholdGroceryAliasInputSchema = z
  .strictObject({
    alias: aliasTextSchema.optional(),
    canonicalKey: canonicalGroceryKeySchema.optional(),
  })
  .refine((value) => value.alias !== undefined || value.canonicalKey !== undefined, {
    message: "At least one alias field must be provided.",
  });

const householdGroceryAliasApiSchema = z
  .strictObject({
    id: z.uuid(),
    household_id: z.uuid(),
    alias: aliasTextSchema,
    canonical_key: canonicalGroceryKeySchema,
    created_by_user_id: z.uuid().nullable(),
    created_at: z.iso.datetime({ offset: true }),
    updated_at: z.iso.datetime({ offset: true }),
  })
  .transform((value) => ({
    id: value.id,
    householdId: value.household_id,
    alias: value.alias,
    canonicalKey: value.canonical_key,
    createdByUserId: value.created_by_user_id,
    createdAt: value.created_at,
    updatedAt: value.updated_at,
  }));

const householdGroceryAliasListApiSchema = z.array(householdGroceryAliasApiSchema);

export type HouseholdGroceryAliasRecord = z.infer<
  typeof householdGroceryAliasApiSchema
>;
export type CreateHouseholdGroceryAliasInput = z.infer<
  typeof createHouseholdGroceryAliasInputSchema
>;
export type UpdateHouseholdGroceryAliasInput = z.infer<
  typeof updateHouseholdGroceryAliasInputSchema
>;

export type AuthenticatedHouseholdAliasRequest = {
  householdId: string;
  accessToken: string;
};

export type CreateHouseholdGroceryAliasRequest = AuthenticatedHouseholdAliasRequest & {
  data: CreateHouseholdGroceryAliasInput;
};

export type UpdateHouseholdGroceryAliasRequest = AuthenticatedHouseholdAliasRequest & {
  aliasId: string;
  data: UpdateHouseholdGroceryAliasInput;
};

export type DeleteHouseholdGroceryAliasRequest = AuthenticatedHouseholdAliasRequest & {
  aliasId: string;
};

function prepareHouseholdRequest({
  householdId,
  accessToken,
}: AuthenticatedHouseholdAliasRequest): {
  collectionPath: string;
  config: AxiosRequestConfig;
} {
  const validated = authenticatedHouseholdRequestSchema.parse({
    householdId,
    accessToken,
  });
  return {
    collectionPath: `/api/v1/households/${validated.householdId}/grocery-aliases`,
    config: {
      headers: { Authorization: `Bearer ${validated.accessToken}` },
    },
  };
}

export async function listHouseholdGroceryAliases(
  request: AuthenticatedHouseholdAliasRequest,
): Promise<HouseholdGroceryAliasRecord[]> {
  const { collectionPath, config } = prepareHouseholdRequest(request);
  const response = await api.get<unknown>(collectionPath, config);
  return householdGroceryAliasListApiSchema.parse(response.data);
}

export async function createHouseholdGroceryAlias(
  request: CreateHouseholdGroceryAliasRequest,
): Promise<HouseholdGroceryAliasRecord> {
  const { collectionPath, config } = prepareHouseholdRequest(request);
  const data = createHouseholdGroceryAliasInputSchema.parse(request.data);
  const response = await api.post<unknown>(
    collectionPath,
    { alias: data.alias, canonical_key: data.canonicalKey },
    config,
  );
  return householdGroceryAliasApiSchema.parse(response.data);
}

export async function updateHouseholdGroceryAlias(
  request: UpdateHouseholdGroceryAliasRequest,
): Promise<HouseholdGroceryAliasRecord> {
  const { collectionPath, config } = prepareHouseholdRequest(request);
  const aliasId = aliasIdSchema.parse(request.aliasId);
  const data = updateHouseholdGroceryAliasInputSchema.parse(request.data);
  const payload: { alias?: string; canonical_key?: GroceryItemKey } = {};
  if (data.alias !== undefined) {
    payload.alias = data.alias;
  }
  if (data.canonicalKey !== undefined) {
    payload.canonical_key = data.canonicalKey;
  }

  const response = await api.patch<unknown>(
    `${collectionPath}/${aliasId}`,
    payload,
    config,
  );
  return householdGroceryAliasApiSchema.parse(response.data);
}

export async function deleteHouseholdGroceryAlias(
  request: DeleteHouseholdGroceryAliasRequest,
): Promise<void> {
  const { collectionPath, config } = prepareHouseholdRequest(request);
  const aliasId = aliasIdSchema.parse(request.aliasId);
  await api.delete(`${collectionPath}/${aliasId}`, config);
}
