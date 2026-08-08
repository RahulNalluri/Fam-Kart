import { NotificationPermissionGateway } from "../src/features/notifications/notificationPermissions";
import { DevicePushTokenProvider } from "../src/features/notifications/expoPushToken";
import { InstallationIdStore } from "../src/features/notifications/installationId";
import { PushDeviceApi } from "../src/features/notifications/pushDeviceApi";
import { createPushDeviceManager } from "../src/features/notifications/pushDeviceManager";

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { easConfig: null, expoConfig: null },
}));
jest.mock("expo-device", () => ({ isDevice: false }));
jest.mock("expo-crypto", () => ({ randomUUID: jest.fn() }));
jest.mock("expo-secure-store", () => ({}));
jest.mock("expo-notifications", () => ({
  AndroidImportance: { DEFAULT: 5 },
  IosAuthorizationStatus: { PROVISIONAL: 3 },
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
}));

const accessToken = "manager-access-token";
const installationId = "11111111-1111-4111-8111-111111111111";
const registeredDevice = {
  id: "22222222-2222-4222-8222-222222222222",
  installationId,
  platform: "android" as const,
  isActive: true,
  lastRegisteredAt: "2026-08-08T12:00:00Z",
};

function harness(granted: boolean, canAskAgain: boolean) {
  const permissionGateway: jest.Mocked<NotificationPermissionGateway> = {
    get: jest.fn().mockResolvedValue({ granted, canAskAgain }),
    request: jest.fn().mockResolvedValue({ granted: true, canAskAgain: true }),
  };
  const tokenProvider: jest.Mocked<DevicePushTokenProvider> = {
    get: jest.fn().mockResolvedValue({
      expoPushToken: "ExpoPushToken[manager_token_123456]",
      platform: "android",
    }),
  };
  const installationIdStore: jest.Mocked<InstallationIdStore> = {
    getExisting: jest.fn().mockResolvedValue(installationId),
    getOrCreate: jest.fn().mockResolvedValue(installationId),
  };
  const pushDeviceApi: jest.Mocked<PushDeviceApi> = {
    register: jest.fn().mockResolvedValue(registeredDevice),
    deactivate: jest.fn().mockResolvedValue(undefined),
  };
  return {
    manager: createPushDeviceManager({
      permissionGateway,
      tokenProvider,
      installationIdStore,
      pushDeviceApi,
    }),
    permissionGateway,
    tokenProvider,
    installationIdStore,
    pushDeviceApi,
  };
}

describe("push-device manager", () => {
  it("registers an already-authorized device without prompting", async () => {
    const context = harness(true, true);
    await expect(context.manager.enable(accessToken)).resolves.toEqual({
      status: "registered",
      device: registeredDevice,
    });
    expect(context.permissionGateway.request).not.toHaveBeenCalled();
    expect(context.pushDeviceApi.register).toHaveBeenCalledWith({
      accessToken,
      installationId,
      expoPushToken: "ExpoPushToken[manager_token_123456]",
      platform: "android",
    });
  });

  it("requests permission before registering after explicit enable", async () => {
    const context = harness(false, true);
    await expect(context.manager.enable(accessToken)).resolves.toMatchObject({
      status: "registered",
    });
    expect(context.permissionGateway.request).toHaveBeenCalledTimes(1);
  });

  it.each([
    { canAskAgain: true, expected: "permission_denied" },
    { canAskAgain: false, expected: "permission_blocked" },
  ])("stops when permission remains unavailable", async ({ canAskAgain, expected }) => {
    const context = harness(false, canAskAgain);
    context.permissionGateway.request.mockResolvedValue({
      granted: false,
      canAskAgain,
    });
    await expect(context.manager.enable(accessToken)).resolves.toEqual({
      status: expected,
    });
    expect(context.tokenProvider.get).not.toHaveBeenCalled();
    expect(context.pushDeviceApi.register).not.toHaveBeenCalled();
  });

  it("deactivates a known installation", async () => {
    const context = harness(true, true);
    await expect(context.manager.disable(accessToken)).resolves.toBe(true);
    expect(context.pushDeviceApi.deactivate).toHaveBeenCalledWith(
      accessToken,
      installationId,
    );
  });

  it("does not call the backend when this installation has no ID", async () => {
    const context = harness(true, true);
    context.installationIdStore.getExisting.mockResolvedValue(null);
    await expect(context.manager.disable(accessToken)).resolves.toBe(false);
    expect(context.pushDeviceApi.deactivate).not.toHaveBeenCalled();
  });

  it("preserves token-provider failures for a later retry", async () => {
    const context = harness(true, true);
    context.tokenProvider.get.mockRejectedValue(new Error("Offline"));
    await expect(context.manager.enable(accessToken)).rejects.toThrow("Offline");
    expect(context.installationIdStore.getOrCreate).not.toHaveBeenCalled();
    expect(context.pushDeviceApi.register).not.toHaveBeenCalled();
  });
});
