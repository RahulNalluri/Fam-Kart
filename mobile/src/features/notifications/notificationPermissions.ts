export type NotificationPermissionState = "granted" | "requestable" | "blocked";

export type NotificationPermissionSnapshot = {
  granted: boolean;
  canAskAgain: boolean;
};

export interface NotificationPermissionGateway {
  get(): Promise<NotificationPermissionSnapshot>;
  request(): Promise<NotificationPermissionSnapshot>;
}

export function resolveNotificationPermissionState(
  permission: NotificationPermissionSnapshot,
): NotificationPermissionState {
  if (permission.granted) {
    return "granted";
  }
  return permission.canAskAgain ? "requestable" : "blocked";
}

export async function getNotificationPermissionState(
  gateway: NotificationPermissionGateway,
): Promise<NotificationPermissionState> {
  return resolveNotificationPermissionState(await gateway.get());
}

export async function requestNotificationPermission(
  gateway: NotificationPermissionGateway,
): Promise<NotificationPermissionState> {
  return resolveNotificationPermissionState(await gateway.request());
}
