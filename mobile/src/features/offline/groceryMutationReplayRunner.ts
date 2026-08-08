import axios, { AxiosRequestConfig } from "axios";

import api from "../../services/api";
import {
  LocalMutationQueueRepository,
  QueuedOfflineMutation,
} from "./localMutationQueueRepository";
import {
  applyServerReconciliation,
  decideServerReconciliation,
  RefreshServerGroceryState,
} from "./serverReconciliation";
import { HouseholdSyncRunner, SyncRunResult } from "./syncCoordinator";

const DEFAULT_REPLAY_LIMIT = 100;
const MAX_REPLAY_LIMIT = 100;

export type GroceryMutationHttpResponse = Readonly<{ status: number }>;

export type GroceryMutationHttpClient = Readonly<{
  post(
    url: string,
    data: unknown,
    config: AxiosRequestConfig,
  ): Promise<GroceryMutationHttpResponse>;
  patch(
    url: string,
    data: unknown,
    config: AxiosRequestConfig,
  ): Promise<GroceryMutationHttpResponse>;
  delete(url: string, config: AxiosRequestConfig): Promise<GroceryMutationHttpResponse>;
}>;

type ReplayQueue = Pick<
  LocalMutationQueueRepository,
  | "listPending"
  | "recordRetry"
  | "requireReview"
  | "removeAcknowledged"
  | "removeDiscarded"
>;

export type GroceryMutationReplayRunnerOptions = Readonly<{
  queue: ReplayQueue;
  getAccessToken: () => string | null;
  refreshServerState: RefreshServerGroceryState;
  httpClient?: GroceryMutationHttpClient;
  replayLimit?: number;
}>;

const defaultHttpClient: GroceryMutationHttpClient = {
  post: (url, data, config) => api.post(url, data, config),
  patch: (url, data, config) => api.patch(url, data, config),
  delete: (url, config) => api.delete(url, config),
};

function validateReplayLimit(limit: number): void {
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_REPLAY_LIMIT) {
    throw new Error(`Offline replay limit must be between 1 and ${MAX_REPLAY_LIMIT}.`);
  }
}

function mutationCollectionPath(mutation: QueuedOfflineMutation): string {
  const householdId = encodeURIComponent(mutation.householdId);
  const sessionId = encodeURIComponent(mutation.shoppingSessionId);
  return `/api/v1/households/${householdId}/shopping-sessions/${sessionId}/items`;
}

function requestConfig(
  mutation: QueuedOfflineMutation,
  accessToken: string,
): AxiosRequestConfig {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
    "Idempotency-Key": mutation.mutationId,
  };
  if (mutation.operation !== "add" && mutation.baseUpdatedAt !== null) {
    headers["X-Base-Updated-At"] = mutation.baseUpdatedAt;
  }
  return { headers };
}

async function sendMutation(
  mutation: QueuedOfflineMutation,
  accessToken: string,
  httpClient: GroceryMutationHttpClient,
): Promise<number | undefined> {
  const collectionPath = mutationCollectionPath(mutation);
  const itemPath = `${collectionPath}/${encodeURIComponent(mutation.itemId)}`;
  const config = requestConfig(mutation, accessToken);

  try {
    switch (mutation.operation) {
      case "add":
        return (await httpClient.post(collectionPath, mutation.payload, config)).status;
      case "edit":
        return (await httpClient.patch(itemPath, mutation.payload, config)).status;
      case "complete":
      case "reopen":
        return (
          await httpClient.patch(`${itemPath}/${mutation.operation}`, undefined, config)
        ).status;
      case "delete":
        return (await httpClient.delete(itemPath, config)).status;
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      return error.response?.status;
    }
    throw error;
  }
}

export function createGroceryMutationReplayRunner({
  queue,
  getAccessToken,
  refreshServerState,
  httpClient = defaultHttpClient,
  replayLimit = DEFAULT_REPLAY_LIMIT,
}: GroceryMutationReplayRunnerOptions): HouseholdSyncRunner {
  validateReplayLimit(replayLimit);

  return async (householdId: string): Promise<SyncRunResult> => {
    const mutations = await queue.listPending(householdId, replayLimit);
    if (mutations.length === 0) {
      return { outcome: "nothing_to_sync", processedCount: 0 };
    }

    let processedCount = 0;
    for (const mutation of mutations) {
      if (mutation.householdId !== householdId) {
        throw new Error("The offline replay queue returned another household's work.");
      }

      const accessToken = getAccessToken()?.trim();
      if (!accessToken) {
        return { outcome: "authentication_required", processedCount };
      }

      const statusCode =
        mutation.operation !== "add" && mutation.baseUpdatedAt === null
          ? 422
          : await sendMutation(mutation, accessToken, httpClient);
      const result = await applyServerReconciliation(
        mutation,
        decideServerReconciliation(mutation, statusCode),
        queue,
        refreshServerState,
      );
      processedCount += result.processedCount;

      if (result.outcome !== "synchronized") {
        return { ...result, processedCount };
      }
    }

    return { outcome: "synchronized", processedCount };
  };
}
