import Constants from "expo-constants";
import * as Device from "expo-device";
import { getExpoPushTokenAsync } from "expo-notifications";
import { Platform } from "react-native";

export type PushPlatform = "android" | "ios";

export type DevicePushToken = Readonly<{
  expoPushToken: string;
  platform: PushPlatform;
}>;

export interface DevicePushTokenProvider {
  get(): Promise<DevicePushToken>;
}

export class PhysicalDeviceRequiredError extends Error {
  constructor() {
    super("Push notifications require a physical Android or iOS device.");
    this.name = "PhysicalDeviceRequiredError";
  }
}

export class PushProjectConfigurationError extends Error {
  constructor() {
    super("An EAS project ID is required to obtain an Expo push token.");
    this.name = "PushProjectConfigurationError";
  }
}

export type ExpoPushTokenDependencies = {
  isDevice?: boolean;
  platform?: string;
  projectId?: string | null;
  getExpoToken?: (options: { projectId: string }) => Promise<{ data: string }>;
};

function configuredProjectId(): string | null {
  const projectId =
    Constants.easConfig?.projectId ?? Constants.expoConfig?.extra?.eas?.projectId;
  return typeof projectId === "string" && projectId.trim() ? projectId.trim() : null;
}

export function createExpoPushTokenProvider({
  isDevice = Device.isDevice,
  platform = Platform.OS,
  projectId = configuredProjectId(),
  getExpoToken = getExpoPushTokenAsync,
}: ExpoPushTokenDependencies = {}): DevicePushTokenProvider {
  return {
    async get() {
      if (!isDevice || (platform !== "android" && platform !== "ios")) {
        throw new PhysicalDeviceRequiredError();
      }
      const normalizedProjectId = projectId?.trim();
      if (!normalizedProjectId) {
        throw new PushProjectConfigurationError();
      }

      const token = await getExpoToken({ projectId: normalizedProjectId });
      return {
        expoPushToken: token.data,
        platform,
      };
    },
  };
}

export const expoPushTokenProvider = createExpoPushTokenProvider();
