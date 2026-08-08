import {
  getNotificationPermissionState,
  NotificationPermissionGateway,
  requestNotificationPermission,
} from "./notificationPermissions";
import { expoNotificationPermissionGateway } from "./expoNotificationPermissions";
import { DevicePushTokenProvider, expoPushTokenProvider } from "./expoPushToken";
import { InstallationIdStore, secureInstallationIdStore } from "./installationId";
import {
  authenticatedPushDeviceApi,
  PushDeviceApi,
  RegisteredPushDevice,
} from "./pushDeviceApi";

export type EnablePushResult =
  | Readonly<{ status: "registered"; device: RegisteredPushDevice }>
  | Readonly<{ status: "permission_denied" | "permission_blocked" }>;

export type PushDeviceManagerDependencies = {
  permissionGateway?: NotificationPermissionGateway;
  tokenProvider?: DevicePushTokenProvider;
  installationIdStore?: InstallationIdStore;
  pushDeviceApi?: PushDeviceApi;
};

export function createPushDeviceManager({
  permissionGateway = expoNotificationPermissionGateway,
  tokenProvider = expoPushTokenProvider,
  installationIdStore = secureInstallationIdStore,
  pushDeviceApi = authenticatedPushDeviceApi,
}: PushDeviceManagerDependencies = {}) {
  return {
    async enable(accessToken: string): Promise<EnablePushResult> {
      let permissionState = await getNotificationPermissionState(permissionGateway);
      if (permissionState === "requestable") {
        permissionState = await requestNotificationPermission(permissionGateway);
      }
      if (permissionState !== "granted") {
        return {
          status:
            permissionState === "blocked" ? "permission_blocked" : "permission_denied",
        };
      }

      const token = await tokenProvider.get();
      const installationId = await installationIdStore.getOrCreate();
      const device = await pushDeviceApi.register({
        accessToken,
        installationId,
        expoPushToken: token.expoPushToken,
        platform: token.platform,
      });
      return { status: "registered", device };
    },
    async disable(accessToken: string): Promise<boolean> {
      const installationId = await installationIdStore.getExisting();
      if (installationId === null) {
        return false;
      }
      await pushDeviceApi.deactivate(accessToken, installationId);
      return true;
    },
  };
}

export const pushDeviceManager = createPushDeviceManager();
