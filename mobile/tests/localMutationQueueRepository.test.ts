import { LocalDatabaseConnection } from "../src/features/offline/localDatabase";
import {
  LocalMutationQueueRepository,
  NewOfflineMutation,
} from "../src/features/offline/localMutationQueueRepository";

const householdId = "11111111-1111-4111-8111-111111111111";
const mutationId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const itemId = "44444444-4444-4444-8444-444444444444";

const mutation: NewOfflineMutation = {
  mutationId,
  householdId,
  shoppingSessionId: sessionId,
  itemId,
  operation: "edit",
  payload: { name: "Rice", quantity: "5.000" },
  baseUpdatedAt: "2026-08-07T08:00:00Z",
  createdAt: "2026-08-07T08:30:00Z",
};

const mutationRow = {
  mutation_id: mutationId,
  household_id: householdId,
  shopping_session_id: sessionId,
  item_id: itemId,
  operation: "edit" as const,
  payload_json: '{"name":"Rice","quantity":"5.000"}',
  base_updated_at: "2026-08-07T08:00:00Z",
  created_at: "2026-08-07T08:30:00Z",
  attempt_count: 2,
  status: "pending" as const,
  last_error_code: "network_unavailable",
};

function buildHarness() {
  const runAsync = jest.fn().mockResolvedValue({ changes: 1, lastInsertRowId: 0 });
  const getFirstAsync = jest.fn().mockResolvedValue(null);
  const getAllAsync = jest.fn().mockResolvedValue([]);
  const database: LocalDatabaseConnection = {
    execAsync: jest.fn().mockResolvedValue(undefined),
    runAsync,
    getFirstAsync,
    getAllAsync,
    withExclusiveTransactionAsync: jest.fn(),
  };

  return {
    repository: new LocalMutationQueueRepository(database),
    runAsync,
    getFirstAsync,
    getAllAsync,
  };
}

describe("LocalMutationQueueRepository", () => {
  it("enqueues a parameterized mutation with a serialized payload", async () => {
    const harness = buildHarness();

    await harness.repository.enqueue(mutation);

    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "INSERT INTO pending_grocery_mutations",
    );
    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "ON CONFLICT(mutation_id) DO NOTHING",
    );
    expect(harness.runAsync.mock.calls[0][0]).not.toContain("Rice");
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $mutationId: mutationId,
      $householdId: householdId,
      $shoppingSessionId: sessionId,
      $itemId: itemId,
      $operation: "edit",
      $payloadJson: '{"name":"Rice","quantity":"5.000"}',
      $baseUpdatedAt: "2026-08-07T08:00:00Z",
      $createdAt: "2026-08-07T08:30:00Z",
    });
  });

  it("rejects a non-serializable payload before accessing SQLite", async () => {
    const harness = buildHarness();
    const circularPayload: Record<string, unknown> = {};
    circularPayload.self = circularPayload;

    await expect(
      harness.repository.enqueue({ ...mutation, payload: circularPayload }),
    ).rejects.toThrow("must be JSON serializable");
    expect(harness.runAsync).not.toHaveBeenCalled();
  });

  it("lists only pending household mutations in FIFO order", async () => {
    const harness = buildHarness();
    harness.getAllAsync.mockResolvedValueOnce([mutationRow]);

    await expect(harness.repository.listPending(householdId, 25)).resolves.toEqual([
      {
        mutationId,
        householdId,
        shoppingSessionId: sessionId,
        itemId,
        operation: "edit",
        payload: { name: "Rice", quantity: "5.000" },
        baseUpdatedAt: "2026-08-07T08:00:00Z",
        createdAt: "2026-08-07T08:30:00Z",
        attemptCount: 2,
        status: "pending",
        lastErrorCode: "network_unavailable",
      },
    ]);

    expect(harness.getAllAsync.mock.calls[0][0]).toContain("status = 'pending'");
    expect(harness.getAllAsync.mock.calls[0][0]).toContain(
      "ORDER BY created_at ASC, mutation_id ASC",
    );
    expect(harness.getAllAsync.mock.calls[0][1]).toEqual({
      $householdId: householdId,
      $limit: 25,
    });
  });

  it.each([0, 101, 1.5])("rejects invalid replay limit %s", async (limit) => {
    const harness = buildHarness();

    await expect(harness.repository.listPending(householdId, limit)).rejects.toThrow(
      "must be between 1 and 100",
    );
    expect(harness.getAllAsync).not.toHaveBeenCalled();
  });

  it("returns a household-scoped mutation by ID", async () => {
    const harness = buildHarness();
    harness.getFirstAsync.mockResolvedValueOnce(mutationRow);

    await expect(
      harness.repository.getMutation(householdId, mutationId),
    ).resolves.toMatchObject({ mutationId, householdId, attemptCount: 2 });
    expect(harness.getFirstAsync.mock.calls[0][1]).toEqual({
      $mutationId: mutationId,
      $householdId: householdId,
    });
  });

  it("rejects a malformed stored payload without exposing its contents", async () => {
    const harness = buildHarness();
    harness.getFirstAsync.mockResolvedValueOnce({
      ...mutationRow,
      payload_json: "private invalid payload",
    });

    await expect(
      harness.repository.getMutation(householdId, mutationId),
    ).rejects.toThrow("contains an invalid payload");
  });

  it("increments retry count with a safe failure code", async () => {
    const harness = buildHarness();

    await harness.repository.recordRetry(
      householdId,
      mutationId,
      "network_unavailable",
    );

    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "attempt_count = attempt_count + 1",
    );
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $errorCode: "network_unavailable",
      $mutationId: mutationId,
      $householdId: householdId,
    });
  });

  it("moves a conflicting mutation out of the replay list", async () => {
    const harness = buildHarness();

    await harness.repository.requireReview(householdId, mutationId, "server_conflict");

    expect(harness.runAsync.mock.calls[0][0]).toContain("status = 'requires_review'");
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $errorCode: "server_conflict",
      $mutationId: mutationId,
      $householdId: householdId,
    });
  });

  it("rejects unsafe error text before writing it locally", async () => {
    const harness = buildHarness();

    await expect(
      harness.repository.recordRetry(
        householdId,
        mutationId,
        "Server said: secret detail",
      ),
    ).rejects.toThrow("must be safe identifiers");
    expect(harness.runAsync).not.toHaveBeenCalled();
  });

  it("removes only an acknowledged mutation in its household", async () => {
    const harness = buildHarness();

    await harness.repository.removeAcknowledged(householdId, mutationId);

    expect(harness.runAsync.mock.calls[0][0]).toContain(
      "DELETE FROM pending_grocery_mutations",
    );
    expect(harness.runAsync.mock.calls[0][1]).toEqual({
      $mutationId: mutationId,
      $householdId: householdId,
    });
  });
});
