import {
  AndroidImportance,
  getPermissionsAsync,
  IosAuthorizationStatus,
  requestPermissionsAsync,
  setNotificationChannelAsync,
} from "expo-notifications";
import type {
  NotificationChannel,
  NotificationChannelInput,
  NotificationPermissionsRequest,
  NotificationPermissionsStatus,
} from "expo-notifications";
import { Platform } from "react-native";

import {
  NotificationPermissionGateway,
  NotificationPermissionSnapshot,
} from "./notificationPermissions";

export const DEFAULT_NOTIFICATION_CHANNEL_ID = "familykart-updates";

type NotificationPlatform = "android" | "ios" | "web" | "windows" | "macos";

export type ExpoNotificationPermissionDependencies = {
  platform: NotificationPlatform;
  getPermissions(): Promise<NotificationPermissionsStatus>;
  requestPermissions(
    request: NotificationPermissionsRequest,
  ): Promise<NotificationPermissionsStatus>;
  setAndroidChannel(
    channelId: string,
    channel: NotificationChannelInput,
  ): Promise<NotificationChannel | null>;
};

const permissionRequest: NotificationPermissionsRequest = {
  ios: {
    allowAlert: true,
    allowBadge: true,
    allowSound: true,
  },
};

function toPermissionSnapshot(
  permission: NotificationPermissionsStatus,
): NotificationPermissionSnapshot {
  const hasProvisionalIosPermission =
    permission.ios?.status === IosAuthorizationStatus.PROVISIONAL;

  return {
    granted: permission.granted || hasProvisionalIosPermission,
    canAskAgain: permission.canAskAgain,
  };
}

const expoDependencies: ExpoNotificationPermissionDependencies = {
  platform: Platform.OS,
  getPermissions: getPermissionsAsync,
  requestPermissions: requestPermissionsAsync,
  setAndroidChannel: setNotificationChannelAsync,
};

export function createExpoNotificationPermissionGateway(
  dependencies: ExpoNotificationPermissionDependencies = expoDependencies,
): NotificationPermissionGateway {
  return {
    async get() {
      return toPermissionSnapshot(await dependencies.getPermissions());
    },
    async request() {
      if (dependencies.platform === "android") {
        await dependencies.setAndroidChannel(DEFAULT_NOTIFICATION_CHANNEL_ID, {
          name: "FamilyKart updates",
          description: "Shared grocery list and household updates",
          importance: AndroidImportance.DEFAULT,
        });
      }

      return toPermissionSnapshot(
        await dependencies.requestPermissions(permissionRequest),
      );
    },
  };
}

export const expoNotificationPermissionGateway =
  createExpoNotificationPermissionGateway();
