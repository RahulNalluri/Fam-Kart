import { AndroidImportance, IosAuthorizationStatus } from "expo-notifications";
import type {
  NotificationPermissionsStatus,
  PermissionStatus,
} from "expo-notifications";

import {
  createExpoNotificationPermissionGateway,
  DEFAULT_NOTIFICATION_CHANNEL_ID,
  ExpoNotificationPermissionDependencies,
} from "../src/features/notifications/expoNotificationPermissions";

jest.mock("expo-notifications", () => ({
  AndroidImportance: { DEFAULT: 5 },
  IosAuthorizationStatus: { PROVISIONAL: 3 },
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
}));

function permissionResponse(
  granted: boolean,
  canAskAgain: boolean,
  iosStatus?: IosAuthorizationStatus,
): NotificationPermissionsStatus {
  return {
    status: (granted ? "granted" : "undetermined") as PermissionStatus,
    granted,
    expires: "never",
    canAskAgain,
    ios:
      iosStatus === undefined
        ? undefined
        : {
            status: iosStatus,
            allowsDisplayInNotificationCenter: null,
            allowsDisplayOnLockScreen: null,
            allowsDisplayInCarPlay: null,
            allowsAlert: null,
            allowsBadge: null,
            allowsSound: null,
            alertStyle: 0,
          },
  };
}

function buildDependencies(
  platform: ExpoNotificationPermissionDependencies["platform"] = "android",
): jest.Mocked<ExpoNotificationPermissionDependencies> {
  return {
    platform,
    getPermissions: jest.fn(),
    requestPermissions: jest.fn(),
    setAndroidChannel: jest.fn().mockResolvedValue(null),
  };
}

describe("Expo notification permission gateway", () => {
  it("checks current Expo permission without creating a channel or prompting", async () => {
    const dependencies = buildDependencies();
    dependencies.getPermissions.mockResolvedValue(permissionResponse(false, true));
    const gateway = createExpoNotificationPermissionGateway(dependencies);

    await expect(gateway.get()).resolves.toEqual({
      granted: false,
      canAskAgain: true,
    });

    expect(dependencies.setAndroidChannel).not.toHaveBeenCalled();
    expect(dependencies.requestPermissions).not.toHaveBeenCalled();
  });

  it("creates the Android channel before requesting permission", async () => {
    const dependencies = buildDependencies("android");
    dependencies.requestPermissions.mockResolvedValue(permissionResponse(true, true));
    const gateway = createExpoNotificationPermissionGateway(dependencies);

    await expect(gateway.request()).resolves.toEqual({
      granted: true,
      canAskAgain: true,
    });

    expect(dependencies.setAndroidChannel).toHaveBeenCalledWith(
      DEFAULT_NOTIFICATION_CHANNEL_ID,
      {
        name: "FamilyKart updates",
        description: "Shared grocery list and household updates",
        importance: AndroidImportance.DEFAULT,
      },
    );
    expect(dependencies.setAndroidChannel.mock.invocationCallOrder[0]).toBeLessThan(
      dependencies.requestPermissions.mock.invocationCallOrder[0],
    );
  });

  it("requests alert, badge, and sound access", async () => {
    const dependencies = buildDependencies("ios");
    dependencies.requestPermissions.mockResolvedValue(permissionResponse(true, true));
    const gateway = createExpoNotificationPermissionGateway(dependencies);

    await gateway.request();

    expect(dependencies.requestPermissions).toHaveBeenCalledWith({
      ios: {
        allowAlert: true,
        allowBadge: true,
        allowSound: true,
      },
    });
    expect(dependencies.setAndroidChannel).not.toHaveBeenCalled();
  });

  it("treats provisional iOS authorization as usable", async () => {
    const dependencies = buildDependencies("ios");
    dependencies.getPermissions.mockResolvedValue(
      permissionResponse(false, true, IosAuthorizationStatus.PROVISIONAL),
    );
    const gateway = createExpoNotificationPermissionGateway(dependencies);

    await expect(gateway.get()).resolves.toEqual({
      granted: true,
      canAskAgain: true,
    });
  });

  it("does not request permission when Android channel setup fails", async () => {
    const dependencies = buildDependencies("android");
    dependencies.setAndroidChannel.mockRejectedValue(new Error("Channel setup failed"));
    const gateway = createExpoNotificationPermissionGateway(dependencies);

    await expect(gateway.request()).rejects.toThrow("Channel setup failed");

    expect(dependencies.requestPermissions).not.toHaveBeenCalled();
  });
});
