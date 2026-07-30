import { RealtimeEventOrderingTracker } from "../src/services/realtimeEventOrdering";
import { RealtimeEvent } from "../src/types/realtime";

const householdId = "11111111-1111-4111-8111-111111111111";
const firstSessionId = "22222222-2222-4222-8222-222222222222";
const secondSessionId = "33333333-3333-4333-8333-333333333333";

function buildEvent(
  sequenceNumber: number,
  eventNumber: number,
  shoppingSessionId: string = firstSessionId,
): RealtimeEvent {
  const eventPart = eventNumber.toString().padStart(12, "0");
  return {
    schema_version: 1,
    event_id: `44444444-4444-4444-8444-${eventPart}`,
    event_type: "grocery.item_added",
    household_id: householdId,
    occurred_at: "2026-07-30T12:00:00Z",
    payload: {
      shopping_session_id: shoppingSessionId,
      grocery_item_id: "55555555-5555-4555-8555-555555555555",
      actor_user_id: "66666666-6666-4666-8666-666666666666",
      item_name: "Milk",
      sequence_number: sequenceNumber,
    },
  };
}

describe("RealtimeEventOrderingTracker", () => {
  it("uses the first event as a baseline and accepts the next sequence", () => {
    const tracker = new RealtimeEventOrderingTracker();

    expect(tracker.evaluate(buildEvent(7, 1))).toEqual({ status: "accepted" });
    expect(tracker.evaluate(buildEvent(8, 2))).toEqual({ status: "accepted" });
  });

  it("ignores a repeated event ID", () => {
    const tracker = new RealtimeEventOrderingTracker();
    const event = buildEvent(1, 1);

    tracker.evaluate(event);

    expect(tracker.evaluate(event)).toEqual({ status: "duplicate" });
  });

  it("ignores a different event with an older sequence", () => {
    const tracker = new RealtimeEventOrderingTracker();
    tracker.evaluate(buildEvent(5, 1));

    expect(tracker.evaluate(buildEvent(4, 2))).toEqual({
      status: "stale",
      latestSequence: 5,
    });
  });

  it("detects a missing sequence after the baseline", () => {
    const tracker = new RealtimeEventOrderingTracker();
    tracker.evaluate(buildEvent(3, 1));

    expect(tracker.evaluate(buildEvent(6, 2))).toEqual({
      status: "gap",
      expectedSequence: 4,
    });
  });

  it("tracks shopping sessions independently", () => {
    const tracker = new RealtimeEventOrderingTracker();
    tracker.evaluate(buildEvent(10, 1, firstSessionId));

    expect(tracker.evaluate(buildEvent(2, 2, secondSessionId))).toEqual({
      status: "accepted",
    });
  });

  it("resets event IDs and sequence baselines after recovery", () => {
    const tracker = new RealtimeEventOrderingTracker();
    const event = buildEvent(5, 1);
    tracker.evaluate(event);

    tracker.reset();

    expect(tracker.evaluate(event)).toEqual({ status: "accepted" });
  });

  it("bounds remembered event IDs", () => {
    const tracker = new RealtimeEventOrderingTracker(2);
    const oldestEvent = buildEvent(1, 1);
    tracker.evaluate(oldestEvent);
    tracker.evaluate(buildEvent(2, 2));
    tracker.evaluate(buildEvent(3, 3));

    expect(tracker.evaluate(oldestEvent)).toEqual({
      status: "stale",
      latestSequence: 3,
    });
  });

  it("rejects an invalid remembered event limit", () => {
    expect(() => new RealtimeEventOrderingTracker(0)).toThrow(
      "The remembered event limit must be a positive integer.",
    );
  });
});
