import { AxiosResponse } from "axios";

import {
  createHouseholdGroceryAlias,
  deleteHouseholdGroceryAlias,
  listHouseholdGroceryAliases,
  updateHouseholdGroceryAlias,
} from "../src/features/grocery/householdAliasApi";
import {
  buildHouseholdAliasIndex,
  findGroceryWithHouseholdAliases,
} from "../src/features/grocery/householdAliases";
import api from "../src/services/api";

jest.mock("../src/services/api", () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));

const householdId = "11111111-1111-4111-8111-111111111111";
const aliasId = "22222222-2222-4222-8222-222222222222";
const userId = "33333333-3333-4333-8333-333333333333";
const accessToken = "household-alias-access-token";
const collectionPath = `/api/v1/households/${householdId}/grocery-aliases`;
const authorizationConfig = {
  headers: { Authorization: `Bearer ${accessToken}` },
};

const backendAlias = {
  id: aliasId,
  household_id: householdId,
  alias: "Morning milk",
  canonical_key: "milk",
  created_by_user_id: userId,
  created_at: "2026-08-02T12:00:00Z",
  updated_at: "2026-08-02T12:05:00Z",
};

const mobileAlias = {
  id: aliasId,
  householdId,
  alias: "Morning milk",
  canonicalKey: "milk",
  createdByUserId: userId,
  createdAt: "2026-08-02T12:00:00Z",
  updatedAt: "2026-08-02T12:05:00Z",
};

const getMock = api.get as jest.MockedFunction<typeof api.get>;
const postMock = api.post as jest.MockedFunction<typeof api.post>;
const patchMock = api.patch as jest.MockedFunction<typeof api.patch>;
const deleteMock = api.delete as jest.MockedFunction<typeof api.delete>;

function responseWith(data: unknown): AxiosResponse<unknown> {
  return {
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: { headers: {} } as AxiosResponse["config"],
  };
}

describe("mobile household grocery alias API", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("lists aliases with authentication and converts the backend response", async () => {
    getMock.mockResolvedValue(responseWith([backendAlias]));

    await expect(
      listHouseholdGroceryAliases({ householdId, accessToken }),
    ).resolves.toEqual([mobileAlias]);
    expect(getMock).toHaveBeenCalledWith(collectionPath, authorizationConfig);
  });

  it("creates an alias using the backend field names", async () => {
    postMock.mockResolvedValue(responseWith(backendAlias));

    await expect(
      createHouseholdGroceryAlias({
        householdId,
        accessToken,
        data: { alias: "Morning milk", canonicalKey: "milk" },
      }),
    ).resolves.toEqual(mobileAlias);
    expect(postMock).toHaveBeenCalledWith(
      collectionPath,
      { alias: "Morning milk", canonical_key: "milk" },
      authorizationConfig,
    );
  });

  it("updates only the supplied alias fields", async () => {
    const updatedBackendAlias = {
      ...backendAlias,
      canonical_key: "egg",
    };
    patchMock.mockResolvedValue(responseWith(updatedBackendAlias));

    const result = await updateHouseholdGroceryAlias({
      householdId,
      aliasId,
      accessToken,
      data: { canonicalKey: "egg" },
    });

    expect(result.canonicalKey).toBe("egg");
    expect(patchMock).toHaveBeenCalledWith(
      `${collectionPath}/${aliasId}`,
      { canonical_key: "egg" },
      authorizationConfig,
    );
  });

  it("deletes the requested household alias", async () => {
    deleteMock.mockResolvedValue(responseWith(undefined));

    await expect(
      deleteHouseholdGroceryAlias({ householdId, aliasId, accessToken }),
    ).resolves.toBeUndefined();
    expect(deleteMock).toHaveBeenCalledWith(
      `${collectionPath}/${aliasId}`,
      authorizationConfig,
    );
  });

  it("preserves nullable creator attribution", async () => {
    getMock.mockResolvedValue(
      responseWith([{ ...backendAlias, created_by_user_id: null }]),
    );

    const aliases = await listHouseholdGroceryAliases({ householdId, accessToken });

    expect(aliases[0].createdByUserId).toBeNull();
  });

  it("feeds validated API aliases into household grocery lookup", async () => {
    getMock.mockResolvedValue(responseWith([backendAlias]));

    const aliases = await listHouseholdGroceryAliases({ householdId, accessToken });
    const aliasIndex = buildHouseholdAliasIndex(aliases);

    expect(findGroceryWithHouseholdAliases("MORNING MILK", aliasIndex)?.key).toBe(
      "milk",
    );
  });

  it.each([
    [{ ...backendAlias, household_id: "not-a-uuid" }],
    [{ ...backendAlias, canonical_key: "dish_soap" }],
    [{ ...backendAlias, unexpected: true }],
  ])("rejects a malformed backend alias response", async (responseData) => {
    getMock.mockResolvedValue(responseWith(responseData));

    await expect(
      listHouseholdGroceryAliases({ householdId, accessToken }),
    ).rejects.toBeDefined();
  });

  it.each([
    ["not-a-household-id", accessToken],
    [householdId, "   "],
  ])(
    "rejects invalid authentication context before making a request",
    async (invalidHouseholdId, invalidAccessToken) => {
      await expect(
        listHouseholdGroceryAliases({
          householdId: invalidHouseholdId,
          accessToken: invalidAccessToken,
        }),
      ).rejects.toBeDefined();
      expect(getMock).not.toHaveBeenCalled();
    },
  );

  it("rejects invalid mutation input before making a request", async () => {
    await expect(
      createHouseholdGroceryAlias({
        householdId,
        accessToken,
        data: { alias: "   ", canonicalKey: "milk" },
      }),
    ).rejects.toBeDefined();
    await expect(
      updateHouseholdGroceryAlias({
        householdId,
        aliasId,
        accessToken,
        data: {},
      }),
    ).rejects.toBeDefined();

    expect(postMock).not.toHaveBeenCalled();
    expect(patchMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid alias ID before making a mutation request", async () => {
    await expect(
      deleteHouseholdGroceryAlias({
        householdId,
        aliasId: "not-an-alias-id",
        accessToken,
      }),
    ).rejects.toBeDefined();

    expect(deleteMock).not.toHaveBeenCalled();
  });

  it("propagates backend errors for the future UI error policy", async () => {
    const backendError = new Error("Household not found.");
    getMock.mockRejectedValue(backendError);

    await expect(
      listHouseholdGroceryAliases({ householdId, accessToken }),
    ).rejects.toBe(backendError);
  });
});
