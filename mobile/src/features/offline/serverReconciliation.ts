import { QueuedOfflineMutation } from "./localMutationQueueRepository";
import {
  classifySynchronizationFailure,
  SynchronizationFailureReason,
} from "./synchronizationPolicy";
import { SyncRunResult } from "./syncCoordinator";

export type ServerReconciliationAction =
  | "acknowledge"
  | "retry"
  | "pause_for_authentication"
  | "discard_and_refresh"
  | "require_user_review";

export type ServerReconciliationReason =
  "server_acknowledged" | "delete_already_applied" | SynchronizationFailureReason;

export type ServerReconciliationDecision = Readonly<{
  action: ServerReconciliationAction;
  reason: ServerReconciliationReason;
  refreshRequired: boolean;
}>;

type ReconciliationQueue = Readonly<{
  recordRetry(
    householdId: string,
    mutationId: string,
    errorCode: string,
  ): Promise<void>;
  requireReview(
    householdId: string,
    mutationId: string,
    errorCode: string,
  ): Promise<void>;
  removeAcknowledged(householdId: string, mutationId: string): Promise<void>;
  removeDiscarded(householdId: string, mutationId: string): Promise<void>;
}>;

export type RefreshServerGroceryState = (
  householdId: string,
  shoppingSessionId: string,
) => Promise<void>;

export function decideServerReconciliation(
  mutation: QueuedOfflineMutation,
  statusCode?: number,
): ServerReconciliationDecision {
  if (statusCode !== undefined && statusCode >= 200 && statusCode < 300) {
    return {
      action: "acknowledge",
      reason: "server_acknowledged",
      refreshRequired: true,
    };
  }

  if (mutation.operation === "delete" && statusCode === 404) {
    return {
      action: "acknowledge",
      reason: "delete_already_applied",
      refreshRequired: true,
    };
  }

  const failure = classifySynchronizationFailure(statusCode);
  if (failure.action === "reject") {
    return {
      action: "require_user_review",
      reason: failure.reason,
      refreshRequired: true,
    };
  }

  return {
    action: failure.action,
    reason: failure.reason,
    refreshRequired:
      failure.action === "discard_and_refresh" ||
      failure.action === "require_user_review",
  };
}

export async function applyServerReconciliation(
  mutation: QueuedOfflineMutation,
  decision: ServerReconciliationDecision,
  queue: ReconciliationQueue,
  refreshServerState: RefreshServerGroceryState,
): Promise<SyncRunResult> {
  const { householdId, shoppingSessionId, mutationId } = mutation;

  switch (decision.action) {
    case "acknowledge":
      await refreshServerState(householdId, shoppingSessionId);
      await queue.removeAcknowledged(householdId, mutationId);
      return { outcome: "synchronized", processedCount: 1 };
    case "discard_and_refresh":
      await refreshServerState(householdId, shoppingSessionId);
      await queue.removeDiscarded(householdId, mutationId);
      return { outcome: "synchronized", processedCount: 1 };
    case "retry":
      await queue.recordRetry(householdId, mutationId, decision.reason);
      return { outcome: "retry_later", processedCount: 0 };
    case "pause_for_authentication":
      return { outcome: "authentication_required", processedCount: 0 };
    case "require_user_review":
      await queue.requireReview(householdId, mutationId, decision.reason);
      await refreshServerState(householdId, shoppingSessionId);
      return { outcome: "requires_review", processedCount: 0 };
  }
}
