export type OfflineMutationOperation =
  "add" | "edit" | "complete" | "reopen" | "delete";

export type OfflineMutationRecord = Readonly<{
  mutationId: string;
  householdId: string;
  shoppingSessionId: string;
  itemId: string;
  operation: OfflineMutationOperation;
  payload: Readonly<Record<string, unknown>>;
  baseUpdatedAt: string | null;
  createdAt: string;
  attemptCount: number;
}>;

export const OFFLINE_SYNCHRONIZATION_REQUIREMENTS = Object.freeze({
  sourceOfTruth: "server" as const,
  replayOrder: "fifo_per_household" as const,
  clientMutationIdRequired: true,
  versionPreconditionRequired: true,
  removeOnlyAfterAcknowledgement: true,
  refreshAfterReplay: true,
});

export type SynchronizationFailureAction =
  | "retry"
  | "pause_for_authentication"
  | "discard_and_refresh"
  | "require_user_review"
  | "reject";

export type SynchronizationFailureReason =
  | "network_unavailable"
  | "temporary_server_failure"
  | "authentication_required"
  | "resource_unavailable"
  | "server_conflict"
  | "invalid_mutation";

export type SynchronizationFailureDecision = Readonly<{
  action: SynchronizationFailureAction;
  reason: SynchronizationFailureReason;
}>;

export function classifySynchronizationFailure(
  statusCode?: number,
): SynchronizationFailureDecision {
  if (statusCode === undefined) {
    return { action: "retry", reason: "network_unavailable" };
  }

  if ([408, 425, 429].includes(statusCode) || statusCode >= 500) {
    return { action: "retry", reason: "temporary_server_failure" };
  }

  if (statusCode === 401) {
    return {
      action: "pause_for_authentication",
      reason: "authentication_required",
    };
  }

  if (statusCode === 403 || statusCode === 404) {
    return { action: "discard_and_refresh", reason: "resource_unavailable" };
  }

  if (statusCode === 409 || statusCode === 412) {
    return { action: "require_user_review", reason: "server_conflict" };
  }

  return { action: "reject", reason: "invalid_mutation" };
}

export type OfflineConflictDecision =
  "replay" | "acknowledge" | "discard_and_refresh" | "require_user_review";

type OfflineConflictInput = Readonly<{
  operation: OfflineMutationOperation;
  targetExists: boolean;
  baseVersionMatches: boolean;
  mutationAlreadyApplied?: boolean;
}>;

export function resolveOfflineConflict({
  operation,
  targetExists,
  baseVersionMatches,
  mutationAlreadyApplied = false,
}: OfflineConflictInput): OfflineConflictDecision {
  if (mutationAlreadyApplied) {
    return "acknowledge";
  }

  if (operation === "add") {
    return targetExists ? "require_user_review" : "replay";
  }

  if (!targetExists) {
    return operation === "delete" ? "acknowledge" : "discard_and_refresh";
  }

  return baseVersionMatches ? "replay" : "require_user_review";
}
