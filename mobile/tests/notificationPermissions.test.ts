import {
  getNotificationPermissionState,
  NotificationPermissionGateway,
  requestNotificationPermission,
  resolveNotificationPermissionState,
} from "../src/features/notifications/notificationPermissions";

function permission(granted: boolean, canAskAgain: boolean) {
  return { granted, canAskAgain };
}

function buildGateway(
  current = permission(false, true),
  requested = permission(true, true),
): jest.Mocked<NotificationPermissionGateway> {
  return {
    get: jest.fn().mockResolvedValue(current),
    request: jest.fn().mockResolvedValue(requested),
  };
}

describe("notification permissions", () => {
  it.each([
    [permission(true, true), "granted"],
    [permission(false, true), "requestable"],
    [permission(false, false), "blocked"],
  ] as const)("maps the native permission response", (snapshot, expected) => {
    expect(resolveNotificationPermissionState(snapshot)).toBe(expected);
  });

  it("checks permission without opening a system prompt", async () => {
    const gateway = buildGateway();

    await expect(getNotificationPermissionState(gateway)).resolves.toBe("requestable");

    expect(gateway.get).toHaveBeenCalledTimes(1);
    expect(gateway.request).not.toHaveBeenCalled();
  });

  it("requests permission only through the explicit request function", async () => {
    const gateway = buildGateway();

    await expect(requestNotificationPermission(gateway)).resolves.toBe("granted");

    expect(gateway.request).toHaveBeenCalledTimes(1);
    expect(gateway.get).not.toHaveBeenCalled();
  });

  it.each(["get", "request"] as const)(
    "preserves native %s failures for the future UI",
    async (operation) => {
      const gateway = buildGateway();
      gateway[operation].mockRejectedValueOnce(
        new Error(`Native permission ${operation} failed`),
      );

      const action =
        operation === "get"
          ? getNotificationPermissionState(gateway)
          : requestNotificationPermission(gateway);

      await expect(action).rejects.toThrow(`Native permission ${operation} failed`);
    },
  );
});
