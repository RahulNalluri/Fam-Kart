import { LocalDatabaseConnection } from "./localDatabase";
import { OfflineMutationRecord } from "./synchronizationPolicy";

export type NewOfflineMutation = Omit<OfflineMutationRecord, "attemptCount">;

export type QueuedOfflineMutation = OfflineMutationRecord &
  Readonly<{
    status: "pending" | "requires_review";
    lastErrorCode: string | null;
  }>;

type QueuedOfflineMutationRow = Readonly<{
  mutation_id: string;
  household_id: string;
  shopping_session_id: string;
  item_id: string;
  operation: OfflineMutationRecord["operation"];
  payload_json: string;
  base_updated_at: string | null;
  created_at: string;
  attempt_count: number;
  status: QueuedOfflineMutation["status"];
  last_error_code: string | null;
}>;

const SELECT_MUTATION_COLUMNS = `
  mutation_id, household_id, shopping_session_id, item_id, operation,
  payload_json, base_updated_at, created_at, attempt_count, status, last_error_code
`;

const DEFAULT_REPLAY_LIMIT = 100;
const MAX_REPLAY_LIMIT = 100;
const SAFE_ERROR_CODE = /^[a-z0-9_]{1,64}$/;

function serializePayload(payload: Readonly<Record<string, unknown>>): string {
  try {
    const serialized = JSON.stringify(payload);
    if (serialized === undefined) {
      throw new Error();
    }
    return serialized;
  } catch {
    throw new Error("The offline mutation payload must be JSON serializable.");
  }
}

function deserializePayload(serialized: string): Readonly<Record<string, unknown>> {
  try {
    const payload: unknown = JSON.parse(serialized);
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error();
    }
    return payload as Readonly<Record<string, unknown>>;
  } catch {
    throw new Error("A stored offline mutation contains an invalid payload.");
  }
}

function mapMutation(row: QueuedOfflineMutationRow): QueuedOfflineMutation {
  return {
    mutationId: row.mutation_id,
    householdId: row.household_id,
    shoppingSessionId: row.shopping_session_id,
    itemId: row.item_id,
    operation: row.operation,
    payload: deserializePayload(row.payload_json),
    baseUpdatedAt: row.base_updated_at,
    createdAt: row.created_at,
    attemptCount: row.attempt_count,
    status: row.status,
    lastErrorCode: row.last_error_code,
  };
}

function validateReplayLimit(limit: number): void {
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_REPLAY_LIMIT) {
    throw new Error(`Offline replay limit must be between 1 and ${MAX_REPLAY_LIMIT}.`);
  }
}

function validateErrorCode(errorCode: string): void {
  if (!SAFE_ERROR_CODE.test(errorCode)) {
    throw new Error("Offline mutation error codes must be safe identifiers.");
  }
}

export class LocalMutationQueueRepository {
  constructor(private readonly database: LocalDatabaseConnection) {}

  async enqueue(mutation: NewOfflineMutation): Promise<void> {
    const payloadJson = serializePayload(mutation.payload);
    await this.database.runAsync(
      `INSERT INTO pending_grocery_mutations (
         mutation_id, household_id, shopping_session_id, item_id, operation,
         payload_json, base_updated_at, created_at
       ) VALUES (
         $mutationId, $householdId, $shoppingSessionId, $itemId, $operation,
         $payloadJson, $baseUpdatedAt, $createdAt
       )
       ON CONFLICT(mutation_id) DO NOTHING;`,
      {
        $mutationId: mutation.mutationId,
        $householdId: mutation.householdId,
        $shoppingSessionId: mutation.shoppingSessionId,
        $itemId: mutation.itemId,
        $operation: mutation.operation,
        $payloadJson: payloadJson,
        $baseUpdatedAt: mutation.baseUpdatedAt,
        $createdAt: mutation.createdAt,
      },
    );
  }

  async listPending(
    householdId: string,
    limit: number = DEFAULT_REPLAY_LIMIT,
  ): Promise<QueuedOfflineMutation[]> {
    validateReplayLimit(limit);
    const rows = await this.database.getAllAsync<QueuedOfflineMutationRow>(
      `SELECT ${SELECT_MUTATION_COLUMNS}
       FROM pending_grocery_mutations
       WHERE household_id = $householdId AND status = 'pending'
       ORDER BY created_at ASC, mutation_id ASC
       LIMIT $limit;`,
      { $householdId: householdId, $limit: limit },
    );
    return rows.map(mapMutation);
  }

  async getMutation(
    householdId: string,
    mutationId: string,
  ): Promise<QueuedOfflineMutation | null> {
    const row = await this.database.getFirstAsync<QueuedOfflineMutationRow>(
      `SELECT ${SELECT_MUTATION_COLUMNS}
       FROM pending_grocery_mutations
       WHERE mutation_id = $mutationId AND household_id = $householdId;`,
      { $mutationId: mutationId, $householdId: householdId },
    );
    return row === null ? null : mapMutation(row);
  }

  async recordRetry(
    householdId: string,
    mutationId: string,
    errorCode: string,
  ): Promise<void> {
    validateErrorCode(errorCode);
    await this.database.runAsync(
      `UPDATE pending_grocery_mutations
       SET attempt_count = attempt_count + 1,
           status = 'pending',
           last_error_code = $errorCode
       WHERE mutation_id = $mutationId AND household_id = $householdId;`,
      {
        $errorCode: errorCode,
        $mutationId: mutationId,
        $householdId: householdId,
      },
    );
  }

  async requireReview(
    householdId: string,
    mutationId: string,
    errorCode: string,
  ): Promise<void> {
    validateErrorCode(errorCode);
    await this.database.runAsync(
      `UPDATE pending_grocery_mutations
       SET status = 'requires_review', last_error_code = $errorCode
       WHERE mutation_id = $mutationId AND household_id = $householdId;`,
      {
        $errorCode: errorCode,
        $mutationId: mutationId,
        $householdId: householdId,
      },
    );
  }

  async removeAcknowledged(householdId: string, mutationId: string): Promise<void> {
    await this.database.runAsync(
      `DELETE FROM pending_grocery_mutations
       WHERE mutation_id = $mutationId AND household_id = $householdId;`,
      { $mutationId: mutationId, $householdId: householdId },
    );
  }

  async removeDiscarded(householdId: string, mutationId: string): Promise<void> {
    await this.database.runAsync(
      `DELETE FROM pending_grocery_mutations
       WHERE mutation_id = $mutationId AND household_id = $householdId;`,
      { $mutationId: mutationId, $householdId: householdId },
    );
  }
}
