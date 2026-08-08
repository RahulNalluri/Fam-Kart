import {
  createGroceryMutationReplayRunner,
  GroceryMutationHttpClient,
} from "../src/features/offline/groceryMutationReplayRunner";
import { QueuedOfflineMutation } from "../src/features/offline/localMutationQueueRepository";

const householdId = "11111111-1111-4111-8111-111111111111";
const sessionId = "22222222-2222-4222-8222-222222222222";
const itemId = "33333333-3333-4333-8333-333333333333";
const mutationId = "44444444-4444-4444-8444-444444444444";
const accessToken = "offline-access-token";
const collectionPath = `/api/v1/households/${householdId}/shopping-sessions/${sessionId}/items`;
const itemPath = `${collectionPath}/${itemId}`;

function mutation(changes: Partial<QueuedOfflineMutation> = {}): QueuedOfflineMutation {
  return {
    mutationId,
    householdId,
    shoppingSessionId: sessionId,
    itemId,
    operation: "edit",
    payload: { name: "Brown rice" },
    baseUpdatedAt: "2026-08-08T08:00:00Z",
    createdAt: "2026-08-08T08:01:00Z",
    attemptCount: 0,
    status: "pending",
    lastErrorCode: null,
    ...changes,
  };
}

function axiosFailure(status?: number): object {
  return status === undefined
    ? { isAxiosError: true }
    : { isAxiosError: true, response: { status } };
}

function buildHarness(mutations: QueuedOfflineMutation[] = [mutation()]) {
  const queue = {
    listPending: jest.fn().mockResolvedValue(mutations),
    recordRetry: jest.fn().mockResolvedValue(undefined),
    requireReview: jest.fn().mockResolvedValue(undefined),
    removeAcknowledged: jest.fn().mockResolvedValue(undefined),
    removeDiscarded: jest.fn().mockResolvedValue(undefined),
  };
  const httpClient: jest.Mocked<GroceryMutationHttpClient> = {
    post: jest.fn().mockResolvedValue({ status: 201 }),
    patch: jest.fn().mockResolvedValue({ status: 200 }),
    delete: jest.fn().mockResolvedValue({ status: 204 }),
  };
  const refreshServerState = jest.fn().mockResolvedValue(undefined);
  const getAccessToken = jest.fn((): string | null => accessToken);
  const runner = createGroceryMutationReplayRunner({
    queue,
    getAccessToken,
    refreshServerState,
    httpClient,
  });

  return {
    queue,
    httpClient,
    refreshServerState,
    getAccessToken,
    runner,
  };
}

const authenticatedHeaders = {
  Authorization: `Bearer ${accessToken}`,
  "Idempotency-Key": mutationId,
  "X-Base-Updated-At": "2026-08-08T08:00:00Z",
};

describe("production grocery mutation replay runner", () => {
  it("returns without requesting a token when the household queue is empty", async () => {
    const harness = buildHarness([]);

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "nothing_to_sync",
      processedCount: 0,
    });
    expect(harness.queue.listPending).toHaveBeenCalledWith(householdId, 100);
    expect(harness.getAccessToken).not.toHaveBeenCalled();
  });

  it("pauses without changing queued work when no access token is available", async () => {
    const harness = buildHarness();
    harness.getAccessToken.mockReturnValue("   ");

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "authentication_required",
      processedCount: 0,
    });
    expect(harness.httpClient.patch).not.toHaveBeenCalled();
    expect(harness.queue.recordRetry).not.toHaveBeenCalled();
  });

  it("posts an add payload without a base-version header", async () => {
    const harness = buildHarness([
      mutation({
        operation: "add",
        payload: { name: "Milk", quantity: "2.000", unit: "packet" },
        baseUpdatedAt: null,
      }),
    ]);

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "synchronized",
      processedCount: 1,
    });
    expect(harness.httpClient.post).toHaveBeenCalledWith(
      collectionPath,
      { name: "Milk", quantity: "2.000", unit: "packet" },
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Idempotency-Key": mutationId,
        },
      },
    );
  });

  it("patches an edit with idempotency and version-precondition headers", async () => {
    const harness = buildHarness();

    await harness.runner(householdId);

    expect(harness.httpClient.patch).toHaveBeenCalledWith(
      itemPath,
      { name: "Brown rice" },
      { headers: authenticatedHeaders },
    );
  });

  it.each(["complete", "reopen"] as const)(
    "patches the %s action without sending a request body",
    async (operation) => {
      const harness = buildHarness([mutation({ operation, payload: {} })]);

      await harness.runner(householdId);

      expect(harness.httpClient.patch).toHaveBeenCalledWith(
        `${itemPath}/${operation}`,
        undefined,
        { headers: authenticatedHeaders },
      );
    },
  );

  it("deletes the item with the replay safety headers", async () => {
    const harness = buildHarness([mutation({ operation: "delete", payload: {} })]);

    await harness.runner(householdId);

    expect(harness.httpClient.delete).toHaveBeenCalledWith(itemPath, {
      headers: authenticatedHeaders,
    });
  });

  it("moves a versioned mutation without a base timestamp to review", async () => {
    const harness = buildHarness([mutation({ baseUpdatedAt: null })]);

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "requires_review",
      processedCount: 0,
    });
    expect(harness.httpClient.patch).not.toHaveBeenCalled();
    expect(harness.queue.requireReview).toHaveBeenCalledWith(
      householdId,
      mutationId,
      "invalid_mutation",
    );
    expect(harness.refreshServerState).toHaveBeenCalledWith(householdId, sessionId);
  });

  it("processes FIFO mutations sequentially and accumulates acknowledgements", async () => {
    const secondMutationId = "55555555-5555-4555-8555-555555555555";
    const harness = buildHarness([
      mutation(),
      mutation({
        mutationId: secondMutationId,
        operation: "complete",
        payload: {},
        createdAt: "2026-08-08T08:02:00Z",
      }),
    ]);

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "synchronized",
      processedCount: 2,
    });
    expect(harness.refreshServerState).toHaveBeenCalledTimes(2);
    expect(harness.queue.removeAcknowledged).toHaveBeenNthCalledWith(
      1,
      householdId,
      mutationId,
    );
    expect(harness.queue.removeAcknowledged).toHaveBeenNthCalledWith(
      2,
      householdId,
      secondMutationId,
    );
    expect(harness.httpClient.patch.mock.invocationCallOrder[0]).toBeLessThan(
      harness.httpClient.patch.mock.invocationCallOrder[1],
    );
  });

  it.each([
    [undefined, "network_unavailable"],
    [503, "temporary_server_failure"],
  ] as const)(
    "keeps a failed request with status %s queued for retry",
    async (status, reason) => {
      const harness = buildHarness();
      harness.httpClient.patch.mockRejectedValueOnce(axiosFailure(status));

      await expect(harness.runner(householdId)).resolves.toEqual({
        outcome: "retry_later",
        processedCount: 0,
      });
      expect(harness.queue.recordRetry).toHaveBeenCalledWith(
        householdId,
        mutationId,
        reason,
      );
      expect(harness.refreshServerState).not.toHaveBeenCalled();
    },
  );

  it("pauses on a server authentication response without changing the queue", async () => {
    const harness = buildHarness();
    harness.httpClient.patch.mockRejectedValueOnce(axiosFailure(401));

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "authentication_required",
      processedCount: 0,
    });
    expect(harness.queue.recordRetry).not.toHaveBeenCalled();
    expect(harness.queue.requireReview).not.toHaveBeenCalled();
  });

  it("marks a stale mutation for review and stops before later FIFO work", async () => {
    const laterMutation = mutation({
      mutationId: "55555555-5555-4555-8555-555555555555",
      operation: "complete",
      payload: {},
    });
    const harness = buildHarness([mutation(), laterMutation]);
    harness.httpClient.patch.mockRejectedValueOnce(axiosFailure(412));

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "requires_review",
      processedCount: 0,
    });
    expect(harness.queue.requireReview).toHaveBeenCalledWith(
      householdId,
      mutationId,
      "server_conflict",
    );
    expect(harness.refreshServerState).toHaveBeenCalledTimes(1);
    expect(harness.httpClient.patch).toHaveBeenCalledTimes(1);
  });

  it("discards inaccessible stale work after refreshing authoritative state", async () => {
    const harness = buildHarness();
    harness.httpClient.patch.mockRejectedValueOnce(axiosFailure(404));

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "synchronized",
      processedCount: 1,
    });
    expect(harness.refreshServerState).toHaveBeenCalledWith(householdId, sessionId);
    expect(harness.queue.removeDiscarded).toHaveBeenCalledWith(householdId, mutationId);
  });

  it("acknowledges an already-absent delete", async () => {
    const harness = buildHarness([mutation({ operation: "delete", payload: {} })]);
    harness.httpClient.delete.mockRejectedValueOnce(axiosFailure(404));

    await expect(harness.runner(householdId)).resolves.toEqual({
      outcome: "synchronized",
      processedCount: 1,
    });
    expect(harness.queue.removeAcknowledged).toHaveBeenCalledWith(
      householdId,
      mutationId,
    );
  });

  it("rejects cross-household queue results without sending them", async () => {
    const harness = buildHarness([
      mutation({ householdId: "66666666-6666-4666-8666-666666666666" }),
    ]);

    await expect(harness.runner(householdId)).rejects.toThrow(
      "another household's work",
    );
    expect(harness.httpClient.patch).not.toHaveBeenCalled();
  });

  it("surfaces non-Axios client failures instead of misclassifying them", async () => {
    const harness = buildHarness();
    harness.httpClient.patch.mockRejectedValueOnce(new Error("client bug"));

    await expect(harness.runner(householdId)).rejects.toThrow("client bug");
    expect(harness.queue.recordRetry).not.toHaveBeenCalled();
  });

  it.each([0, 101, 1.5])("rejects invalid replay limit %s", (replayLimit) => {
    const harness = buildHarness();

    expect(() =>
      createGroceryMutationReplayRunner({
        queue: harness.queue,
        getAccessToken: harness.getAccessToken,
        refreshServerState: harness.refreshServerState,
        httpClient: harness.httpClient,
        replayLimit,
      }),
    ).toThrow("must be between 1 and 100");
  });
});
