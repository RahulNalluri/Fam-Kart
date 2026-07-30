import { RealtimeEvent } from "../types/realtime";

export type RealtimeEventOrderingDecision =
  | { status: "accepted" }
  | { status: "duplicate" }
  | { status: "stale"; latestSequence: number }
  | { status: "gap"; expectedSequence: number };

const DEFAULT_REMEMBERED_EVENT_LIMIT = 500;

export class RealtimeEventOrderingTracker {
  private readonly rememberedEventLimit: number;
  private readonly rememberedEventIds = new Set<string>();
  private readonly eventIdOrder: string[] = [];
  private readonly latestSequenceBySession = new Map<string, number>();

  constructor(rememberedEventLimit: number = DEFAULT_REMEMBERED_EVENT_LIMIT) {
    if (!Number.isInteger(rememberedEventLimit) || rememberedEventLimit <= 0) {
      throw new Error("The remembered event limit must be a positive integer.");
    }
    this.rememberedEventLimit = rememberedEventLimit;
  }

  evaluate(event: RealtimeEvent): RealtimeEventOrderingDecision {
    if (this.rememberedEventIds.has(event.event_id)) {
      return { status: "duplicate" };
    }
    this.rememberEventId(event.event_id);

    const sessionKey = `${event.household_id}:${event.payload.shopping_session_id}`;
    const sequence = event.payload.sequence_number;
    const latestSequence = this.latestSequenceBySession.get(sessionKey);

    if (latestSequence === undefined) {
      this.latestSequenceBySession.set(sessionKey, sequence);
      return { status: "accepted" };
    }
    if (sequence <= latestSequence) {
      return { status: "stale", latestSequence };
    }

    this.latestSequenceBySession.set(sessionKey, sequence);
    if (sequence > latestSequence + 1) {
      return { status: "gap", expectedSequence: latestSequence + 1 };
    }
    return { status: "accepted" };
  }

  reset(): void {
    this.rememberedEventIds.clear();
    this.eventIdOrder.length = 0;
    this.latestSequenceBySession.clear();
  }

  private rememberEventId(eventId: string): void {
    this.rememberedEventIds.add(eventId);
    this.eventIdOrder.push(eventId);
    if (this.eventIdOrder.length > this.rememberedEventLimit) {
      const oldestEventId = this.eventIdOrder.shift();
      if (oldestEventId !== undefined) {
        this.rememberedEventIds.delete(oldestEventId);
      }
    }
  }
}
