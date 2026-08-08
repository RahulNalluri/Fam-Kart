import { AxiosResponse } from "axios";

import { authenticatedPushDeviceApi } from "../src/features/notifications/pushDeviceApi";
import api from "../src/services/api";

jest.mock("../src/services/api", () => ({
  __esModule: true,
  default: { put: jest.fn(), delete: jest.fn() },
}));

const accessToken = "push-access-token";
const installationId = "11111111-1111-4111-8111-111111111111";
const deviceId = "22222222-2222-4222-8222-222222222222";
const expoPushToken = "ExponentPushToken[mobile_token_123456]";
const backendDevice = {
  id: deviceId,
  installation_id: installationId,
  platform: "android",
  is_active: true,
  last_registered_at: "2026-08-08T12:00:00Z",
  created_at: "2026-08-08T12:00:00Z",
  updated_at: "2026-08-08T12:00:00Z",
};

function response(data: unknown): AxiosResponse<unknown> {
  return {
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: { headers: {} } as AxiosResponse["config"],
  };
}

describe("authenticated push-device API", () => {
  beforeEach(() => jest.clearAllMocks());

  it("registers a validated token using bearer authentication", async () => {
    jest.mocked(api.put).mockResolvedValue(response(backendDevice));

    await expect(
      authenticatedPushDeviceApi.register({
        accessToken,
        installationId,
        expoPushToken,
        platform: "android",
      }),
    ).resolves.toEqual({
      id: deviceId,
      installationId,
      platform: "android",
      isActive: true,
      lastRegisteredAt: "2026-08-08T12:00:00Z",
    });
    expect(api.put).toHaveBeenCalledWith(
      "/api/v1/users/me/push-devices",
      {
        installation_id: installationId,
        expo_push_token: expoPushToken,
        platform: "android",
      },
      { headers: { Authorization: `Bearer ${accessToken}` } },
    );
  });

  it("deactivates only the current installation", async () => {
    jest.mocked(api.delete).mockResolvedValue(response(undefined));
    await authenticatedPushDeviceApi.deactivate(accessToken, installationId);
    expect(api.delete).toHaveBeenCalledWith(
      `/api/v1/users/me/push-devices/${installationId}`,
      { headers: { Authorization: `Bearer ${accessToken}` } },
    );
  });

  it.each([
    { accessToken: "", installationId, expoPushToken, platform: "android" as const },
    { accessToken, installationId: "bad", expoPushToken, platform: "android" as const },
    {
      accessToken,
      installationId,
      expoPushToken: "native-token",
      platform: "ios" as const,
    },
  ])("rejects invalid registration data before HTTP", async (input) => {
    await expect(authenticatedPushDeviceApi.register(input)).rejects.toThrow();
    expect(api.put).not.toHaveBeenCalled();
  });

  it("rejects malformed server data", async () => {
    jest
      .mocked(api.put)
      .mockResolvedValue(response({ ...backendDevice, platform: "web" }));
    await expect(
      authenticatedPushDeviceApi.register({
        accessToken,
        installationId,
        expoPushToken,
        platform: "android",
      }),
    ).rejects.toThrow();
  });
});
