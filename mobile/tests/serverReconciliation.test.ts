import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";
import {
  applyServerReconciliation,
  decideServerReconciliation,
  ServerReconciliationDecision,
} from "../src/features/offline/serverReconciliation";

const mutation: QueuedOfflineMutation = {
  mutationId: "11111111-1111-4111-8111-111111111111",
  householdId: "22222222-2222-4222-8222-222222222222",
  shoppingSessionId: "33333333-3333-4333-8333-333333333333",
  itemId: "44444444-4444-4444-8444-444444444444",
  operation: "edit",
  payload: { name: "Brown rice" },
  baseUpdatedAt: "2026-08-08T08:00:00Z",
  createdAt: "2026-08-08T08:01:00Z",
  attemptCount: 0,
  status: "pending",
  lastErrorCode: null,
};

function buildEffects() {
  return {
    queue: {
      recordRetry: jest.fn().mockResolvedValue(undefined),
      requireReview: jest.fn().mockResolvedValue(undefined),
      removeAcknowledged: jest.fn().mockResolvedValue(undefined),
      removeDiscarded: jest.fn().mockResolvedValue(undefined),
    },
    refresh: jest.fn().mockResolvedValue(undefined),
  };
}

describe("server reconciliation decisions", () => {
  it.each([200, 201, 204])("acknowledges successful status %s", (statusCode) => {
    expect(decideServerReconciliation(mutation, statusCode)).toEqual({
      action: "acknowledge",
      reason: "server_acknowledged",
      refreshRequired: true,
    });
  });

  it("acknowledges a delete when its target is already absent", () => {
    expect(
      decideServerReconciliation({ ...mutation, operation: "delete" }, 404),
    ).toEqual({
      action: "acknowledge",
      reason: "delete_already_applied",
      refreshRequired: true,
    });
  });

  it("discards and refreshes an edit whose target is inaccessible", () => {
    expect(decideServerReconciliation(mutation, 404)).toEqual({
      action: "discard_and_refresh",
      reason: "resource_unavailable",
      refreshRequired: true,
    });
  });

  it.each([409, 412])("requires review for server conflict %s", (statusCode) => {
    expect(decideServerReconciliation(mutation, statusCode)).toEqual({
      action: "require_user_review",
      reason: "server_conflict",
      refreshRequired: true,
    });
  });

  it("retains temporary network failures for retry", () => {
    expect(decideServerReconciliation(mutation)).toEqual({
      action: "retry",
      reason: "network_unavailable",
      refreshRequired: false,
    });
  });

  it("pauses without changing queued work when authentication is required", () => {
    expect(decideServerReconciliation(mutation, 401)).toEqual({
      action: "pause_for_authentication",
      reason: "authentication_required",
      refreshRequired: false,
    });
  });

  it("moves a permanently invalid mutation to review instead of retrying forever", () => {
    expect(decideServerReconciliation(mutation, 422)).toEqual({
      action: "require_user_review",
      reason: "invalid_mutation",
      refreshRequired: true,
    });
  });
});

describe("server reconciliation effects", () => {
  async function apply(decision: ServerReconciliationDecision) {
    const effects = buildEffects();
    const result = await applyServerReconciliation(
      mutation,
      decision,
      effects.queue,
      effects.refresh,
    );
    return { ...effects, result };
  }

  it("refreshes authoritative state before removing acknowledged work", async () => {
    const effects = await apply(decideServerReconciliation(mutation, 200));

    expect(effects.result).toEqual({ outcome: "synchronized", processedCount: 1 });
    expect(effects.refresh).toHaveBeenCalledWith(
      mutation.householdId,
      mutation.shoppingSessionId,
    );
    expect(effects.queue.removeAcknowledged).toHaveBeenCalledWith(
      mutation.householdId,
      mutation.mutationId,
    );
    expect(effects.refresh.mock.invocationCallOrder[0]).toBeLessThan(
      effects.queue.removeAcknowledged.mock.invocationCallOrder[0],
    );
  });

  it("keeps acknowledged work queued when the server refresh fails", async () => {
    const effects = buildEffects();
    effects.refresh.mockRejectedValueOnce(new Error("refresh unavailable"));

    await expect(
      applyServerReconciliation(
        mutation,
        decideServerReconciliation(mutation, 200),
        effects.queue,
        effects.refresh,
      ),
    ).rejects.toThrow("refresh unavailable");
    expect(effects.queue.removeAcknowledged).not.toHaveBeenCalled();
  });

  it("removes inaccessible stale work only after refreshing", async () => {
    const effects = await apply(decideServerReconciliation(mutation, 404));

    expect(effects.result).toEqual({ outcome: "synchronized", processedCount: 1 });
    expect(effects.queue.removeDiscarded).toHaveBeenCalledWith(
      mutation.householdId,
      mutation.mutationId,
    );
  });

  it("records retry state without refreshing or removing the mutation", async () => {
    const effects = await apply(decideServerReconciliation(mutation, 503));

    expect(effects.result).toEqual({ outcome: "retry_later", processedCount: 0 });
    expect(effects.queue.recordRetry).toHaveBeenCalledWith(
      mutation.householdId,
      mutation.mutationId,
      "temporary_server_failure",
    );
    expect(effects.refresh).not.toHaveBeenCalled();
    expect(effects.queue.removeAcknowledged).not.toHaveBeenCalled();
  });

  it("marks conflicts for review and refreshes the visible server state", async () => {
    const effects = await apply(decideServerReconciliation(mutation, 412));

    expect(effects.result).toEqual({ outcome: "requires_review", processedCount: 0 });
    expect(effects.queue.requireReview).toHaveBeenCalledWith(
      mutation.householdId,
      mutation.mutationId,
      "server_conflict",
    );
    expect(effects.refresh).toHaveBeenCalledTimes(1);
  });

  it("pauses for authentication without changing local persistence", async () => {
    const effects = await apply(decideServerReconciliation(mutation, 401));

    expect(effects.result).toEqual({
      outcome: "authentication_required",
      processedCount: 0,
    });
    expect(effects.refresh).not.toHaveBeenCalled();
    expect(effects.queue.recordRetry).not.toHaveBeenCalled();
    expect(effects.queue.requireReview).not.toHaveBeenCalled();
  });
});
