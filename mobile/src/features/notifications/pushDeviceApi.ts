import { z } from "zod";

import api from "../../services/api";
import { PushPlatform } from "./expoPushToken";

const expoPushTokenSchema = z
  .string()
  .min(20)
  .max(255)
  .regex(/^Expo(?:nent)?PushToken\[[A-Za-z0-9_-]+\]$/);

const registerPushDeviceSchema = z.strictObject({
  accessToken: z.string().trim().min(1),
  installationId: z.uuid(),
  expoPushToken: expoPushTokenSchema,
  platform: z.enum(["android", "ios"]),
});

const pushDeviceApiSchema = z.strictObject({
  id: z.uuid(),
  installation_id: z.uuid(),
  platform: z.enum(["android", "ios"]),
  is_active: z.boolean(),
  last_registered_at: z.iso.datetime({ offset: true }),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

export type RegisteredPushDevice = Readonly<{
  id: string;
  installationId: string;
  platform: PushPlatform;
  isActive: boolean;
  lastRegisteredAt: string;
}>;

export interface PushDeviceApi {
  register(input: {
    accessToken: string;
    installationId: string;
    expoPushToken: string;
    platform: PushPlatform;
  }): Promise<RegisteredPushDevice>;
  deactivate(accessToken: string, installationId: string): Promise<void>;
}

export const authenticatedPushDeviceApi: PushDeviceApi = {
  async register(input) {
    const validated = registerPushDeviceSchema.parse(input);
    const response = await api.put<unknown>(
      "/api/v1/users/me/push-devices",
      {
        installation_id: validated.installationId,
        expo_push_token: validated.expoPushToken,
        platform: validated.platform,
      },
      {
        headers: { Authorization: `Bearer ${validated.accessToken}` },
      },
    );
    const device = pushDeviceApiSchema.parse(response.data);
    return {
      id: device.id,
      installationId: device.installation_id,
      platform: device.platform,
      isActive: device.is_active,
      lastRegisteredAt: device.last_registered_at,
    };
  },
  async deactivate(accessToken, installationId) {
    const validatedToken = z.string().trim().min(1).parse(accessToken);
    const validatedInstallationId = z.uuid().parse(installationId);
    await api.delete(
      `/api/v1/users/me/push-devices/${encodeURIComponent(validatedInstallationId)}`,
      {
        headers: { Authorization: `Bearer ${validatedToken}` },
      },
    );
  },
};
