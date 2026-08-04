import {
  ensureMicrophonePermission,
  getMicrophonePermissionState,
  MicrophonePermissionGateway,
  requestMicrophonePermission,
  resolveMicrophonePermissionState,
} from "../src/features/voice/microphonePermissions";

function permission(granted: boolean, canAskAgain: boolean) {
  return { granted, canAskAgain };
}

function buildGateway(
  current = permission(false, true),
  requested = permission(true, true),
): jest.Mocked<MicrophonePermissionGateway> {
  return {
    get: jest.fn().mockResolvedValue(current),
    request: jest.fn().mockResolvedValue(requested),
  };
}

describe("microphone permissions", () => {
  it.each([
    [permission(true, true), "granted"],
    [permission(false, true), "requestable"],
    [permission(false, false), "blocked"],
  ] as const)("maps the native response to %s", (snapshot, expected) => {
    expect(resolveMicrophonePermissionState(snapshot)).toBe(expected);
  });

  it("checks permission without opening a system prompt", async () => {
    const gateway = buildGateway(permission(false, true));

    await expect(getMicrophonePermissionState(gateway)).resolves.toBe("requestable");

    expect(gateway.get).toHaveBeenCalledTimes(1);
    expect(gateway.request).not.toHaveBeenCalled();
  });

  it("requests permission through the native gateway", async () => {
    const gateway = buildGateway(permission(false, true), permission(true, true));

    await expect(requestMicrophonePermission(gateway)).resolves.toBe("granted");

    expect(gateway.request).toHaveBeenCalledTimes(1);
  });

  it("requests once when the operating system can still ask", async () => {
    const gateway = buildGateway(permission(false, true), permission(false, false));

    await expect(ensureMicrophonePermission(gateway)).resolves.toBe("blocked");

    expect(gateway.get).toHaveBeenCalledTimes(1);
    expect(gateway.request).toHaveBeenCalledTimes(1);
  });

  it.each([
    [permission(true, true), "granted"],
    [permission(false, false), "blocked"],
  ] as const)(
    "does not request again when the current state is %s",
    async (snapshot, expected) => {
      const gateway = buildGateway(snapshot);

      await expect(ensureMicrophonePermission(gateway)).resolves.toBe(expected);

      expect(gateway.get).toHaveBeenCalledTimes(1);
      expect(gateway.request).not.toHaveBeenCalled();
    },
  );

  it("preserves native permission failures for the future UI", async () => {
    const gateway = buildGateway();
    gateway.get.mockRejectedValueOnce(new Error("Native permission check failed"));

    await expect(ensureMicrophonePermission(gateway)).rejects.toThrow(
      "Native permission check failed",
    );

    expect(gateway.request).not.toHaveBeenCalled();
  });
});
