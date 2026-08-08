import {
  createExpoPushTokenProvider,
  PhysicalDeviceRequiredError,
  PushProjectConfigurationError,
} from "../src/features/notifications/expoPushToken";

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { easConfig: null, expoConfig: null },
}));
jest.mock("expo-device", () => ({ isDevice: false }));
jest.mock("expo-notifications", () => ({ getExpoPushTokenAsync: jest.fn() }));

describe("Expo push-token provider", () => {
  it.each(["android", "ios"] as const)(
    "obtains an Expo token for a physical %s device",
    async (platform) => {
      const getExpoToken = jest.fn().mockResolvedValue({
        data: "ExponentPushToken[test_token_123456]",
      });
      const provider = createExpoPushTokenProvider({
        isDevice: true,
        platform,
        projectId: "project-id",
        getExpoToken,
      });

      await expect(provider.get()).resolves.toEqual({
        expoPushToken: "ExponentPushToken[test_token_123456]",
        platform,
      });
      expect(getExpoToken).toHaveBeenCalledWith({ projectId: "project-id" });
    },
  );

  it.each([
    { isDevice: false, platform: "android" },
    { isDevice: true, platform: "web" },
  ])("rejects unsupported device context", async (context) => {
    const provider = createExpoPushTokenProvider({
      ...context,
      projectId: "project-id",
    });
    await expect(provider.get()).rejects.toBeInstanceOf(PhysicalDeviceRequiredError);
  });

  it.each([null, "", "   "])("rejects missing project ID %s", async (projectId) => {
    const provider = createExpoPushTokenProvider({
      isDevice: true,
      platform: "android",
      projectId,
    });
    await expect(provider.get()).rejects.toBeInstanceOf(PushProjectConfigurationError);
  });

  it("preserves network failures for retry handling", async () => {
    const provider = createExpoPushTokenProvider({
      isDevice: true,
      platform: "ios",
      projectId: "project-id",
      getExpoToken: jest.fn().mockRejectedValue(new Error("Expo unavailable")),
    });
    await expect(provider.get()).rejects.toThrow("Expo unavailable");
  });
});
