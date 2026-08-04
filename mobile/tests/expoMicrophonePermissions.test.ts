import {
  getRecordingPermissionsAsync,
  requestRecordingPermissionsAsync,
} from "expo-audio";
import type { PermissionResponse } from "expo-audio";

import { expoMicrophonePermissionGateway } from "../src/features/voice/expoMicrophonePermissions";

jest.mock("expo-audio", () => ({
  getRecordingPermissionsAsync: jest.fn(),
  requestRecordingPermissionsAsync: jest.fn(),
}));

const mockGetRecordingPermissionsAsync = jest.mocked(getRecordingPermissionsAsync);
const mockRequestRecordingPermissionsAsync = jest.mocked(
  requestRecordingPermissionsAsync,
);

function permissionResponse(
  granted: boolean,
  canAskAgain: boolean,
): PermissionResponse {
  return {
    status: (granted ? "granted" : "undetermined") as PermissionResponse["status"],
    granted,
    expires: "never",
    canAskAgain,
  };
}

describe("Expo microphone permission gateway", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("checks permission through Expo Audio", async () => {
    const response = permissionResponse(false, true);
    mockGetRecordingPermissionsAsync.mockResolvedValue(response);

    await expect(expoMicrophonePermissionGateway.get()).resolves.toBe(response);

    expect(mockGetRecordingPermissionsAsync).toHaveBeenCalledTimes(1);
  });

  it("requests permission through Expo Audio", async () => {
    const response = permissionResponse(true, true);
    mockRequestRecordingPermissionsAsync.mockResolvedValue(response);

    await expect(expoMicrophonePermissionGateway.request()).resolves.toBe(response);

    expect(mockRequestRecordingPermissionsAsync).toHaveBeenCalledTimes(1);
  });
});
