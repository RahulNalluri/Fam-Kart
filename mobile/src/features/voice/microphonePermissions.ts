export type MicrophonePermissionState = "granted" | "requestable" | "blocked";

export type MicrophonePermissionSnapshot = {
  granted: boolean;
  canAskAgain: boolean;
};

export interface MicrophonePermissionGateway {
  get(): Promise<MicrophonePermissionSnapshot>;
  request(): Promise<MicrophonePermissionSnapshot>;
}

export function resolveMicrophonePermissionState(
  permission: MicrophonePermissionSnapshot,
): MicrophonePermissionState {
  if (permission.granted) {
    return "granted";
  }
  return permission.canAskAgain ? "requestable" : "blocked";
}

export async function getMicrophonePermissionState(
  gateway: MicrophonePermissionGateway,
): Promise<MicrophonePermissionState> {
  return resolveMicrophonePermissionState(await gateway.get());
}

export async function requestMicrophonePermission(
  gateway: MicrophonePermissionGateway,
): Promise<MicrophonePermissionState> {
  return resolveMicrophonePermissionState(await gateway.request());
}

export async function ensureMicrophonePermission(
  gateway: MicrophonePermissionGateway,
): Promise<MicrophonePermissionState> {
  const currentState = await getMicrophonePermissionState(gateway);
  if (currentState !== "requestable") {
    return currentState;
  }
  return requestMicrophonePermission(gateway);
}
