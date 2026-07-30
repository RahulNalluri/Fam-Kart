import { z } from "zod";

export const realtimeEventTypes = [
  "grocery.item_added",
  "grocery.item_edited",
  "grocery.item_completed",
  "grocery.item_reopened",
  "grocery.item_deleted",
] as const;

export const groceryItemRealtimePayloadSchema = z.strictObject({
  shopping_session_id: z.uuid(),
  grocery_item_id: z.uuid(),
  actor_user_id: z.uuid().nullable(),
  item_name: z
    .string()
    .min(1)
    .max(160)
    .refine((value) => value.trim().length > 0),
  sequence_number: z.number().int().positive(),
});

export const realtimeEventSchema = z.strictObject({
  schema_version: z.literal(1),
  event_id: z.uuid(),
  event_type: z.enum(realtimeEventTypes),
  household_id: z.uuid(),
  occurred_at: z.iso.datetime({ offset: true }),
  payload: groceryItemRealtimePayloadSchema,
});

export type RealtimeEvent = z.infer<typeof realtimeEventSchema>;
export type RealtimeEventType = RealtimeEvent["event_type"];
