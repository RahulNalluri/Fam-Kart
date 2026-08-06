import {
  classifySynchronizationFailure,
  OFFLINE_SYNCHRONIZATION_REQUIREMENTS,
  resolveOfflineConflict,
} from "../src/features/offline/synchronizationPolicy";

describe("offline synchronization requirements", () => {
  it("requires safe server acknowledgement and conflict controls", () => {
    expect(OFFLINE_SYNCHRONIZATION_REQUIREMENTS).toEqual({
      sourceOfTruth: "server",
      replayOrder: "fifo_per_household",
      clientMutationIdRequired: true,
      versionPreconditionRequired: true,
      removeOnlyAfterAcknowledgement: true,
      refreshAfterReplay: true,
    });
  });
});

describe("offline synchronization failure policy", () => {
  it.each([undefined, 408, 425, 429, 500, 503])(
    "retries a temporary failure represented by %s",
    (statusCode) => {
      expect(classifySynchronizationFailure(statusCode).action).toBe("retry");
    },
  );

  it("pauses queued work when the access token must be refreshed", () => {
    expect(classifySynchronizationFailure(401)).toEqual({
      action: "pause_for_authentication",
      reason: "authentication_required",
    });
  });

  it.each([403, 404])(
    "discards inaccessible resource work for status %s and requires a refresh",
    (statusCode) => {
      expect(classifySynchronizationFailure(statusCode)).toEqual({
        action: "discard_and_refresh",
        reason: "resource_unavailable",
      });
    },
  );

  it.each([409, 412])("sends status %s conflicts for review", (statusCode) => {
    expect(classifySynchronizationFailure(statusCode)).toEqual({
      action: "require_user_review",
      reason: "server_conflict",
    });
  });

  it.each([400, 418, 422])("rejects permanent status %s failures", (statusCode) => {
    expect(classifySynchronizationFailure(statusCode)).toEqual({
      action: "reject",
      reason: "invalid_mutation",
    });
  });
});

describe("offline conflict policy", () => {
  it("acknowledges a mutation the server already processed", () => {
    expect(
      resolveOfflineConflict({
        operation: "add",
        targetExists: true,
        baseVersionMatches: false,
        mutationAlreadyApplied: true,
      }),
    ).toBe("acknowledge");
  });

  it("replays a new add when its target does not exist", () => {
    expect(
      resolveOfflineConflict({
        operation: "add",
        targetExists: false,
        baseVersionMatches: false,
      }),
    ).toBe("replay");
  });

  it("does not silently overwrite an existing item with an offline add", () => {
    expect(
      resolveOfflineConflict({
        operation: "add",
        targetExists: true,
        baseVersionMatches: false,
      }),
    ).toBe("require_user_review");
  });

  it("replays an update only when its server version is unchanged", () => {
    expect(
      resolveOfflineConflict({
        operation: "edit",
        targetExists: true,
        baseVersionMatches: true,
      }),
    ).toBe("replay");
  });

  it("requires review instead of overwriting a newer server update", () => {
    expect(
      resolveOfflineConflict({
        operation: "complete",
        targetExists: true,
        baseVersionMatches: false,
      }),
    ).toBe("require_user_review");
  });

  it("accepts an already-deleted target as a successful delete", () => {
    expect(
      resolveOfflineConflict({
        operation: "delete",
        targetExists: false,
        baseVersionMatches: false,
      }),
    ).toBe("acknowledge");
  });

  it("discards a stale edit when another member deleted its target", () => {
    expect(
      resolveOfflineConflict({
        operation: "edit",
        targetExists: false,
        baseVersionMatches: false,
      }),
    ).toBe("discard_and_refresh");
  });
});
