import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { getLocalDatabase } from "../features/offline/localDatabase";
import {
  LocalMutationQueueRepository,
  QueuedOfflineMutation,
} from "../features/offline/localMutationQueueRepository";
import { refreshShoppingSessionGroceryQueries } from "../features/grocery/realtimeSynchronization";

type ConflictReviewRepository = Pick<
  LocalMutationQueueRepository,
  "listRequiresReview" | "resolveReviewByKeepingServerVersion"
>;

export type ConflictReviewError = "load_failed" | "resolve_failed";

export type GroceryConflictReviewDependencies = Readonly<{
  getRepository: () => Promise<ConflictReviewRepository>;
}>;

export type UseGroceryConflictReviewOptions = Readonly<{
  householdId: string | null;
  dependencies?: GroceryConflictReviewDependencies;
  onError?: (error: unknown) => void;
}>;

export type GroceryConflictReviewState = Readonly<{
  conflicts: readonly QueuedOfflineMutation[];
  loading: boolean;
  resolvingMutationId: string | null;
  error: ConflictReviewError | null;
  refresh: () => Promise<void>;
  keepFamilyVersion: (mutationId: string) => Promise<boolean>;
}>;

async function getDefaultRepository(): Promise<ConflictReviewRepository> {
  return new LocalMutationQueueRepository(await getLocalDatabase());
}

const defaultDependencies: GroceryConflictReviewDependencies = {
  getRepository: getDefaultRepository,
};

export function useGroceryConflictReview({
  householdId,
  dependencies = defaultDependencies,
  onError,
}: UseGroceryConflictReviewOptions): GroceryConflictReviewState {
  const queryClient = useQueryClient();
  const errorHandlerRef = useRef(onError);
  const generationRef = useRef(0);
  const resolvingRef = useRef(false);
  const conflictsRef = useRef<readonly QueuedOfflineMutation[]>([]);
  errorHandlerRef.current = onError;

  const [conflicts, setConflicts] = useState<readonly QueuedOfflineMutation[]>([]);
  const [loading, setLoading] = useState(false);
  const [resolvingMutationId, setResolvingMutationId] = useState<string | null>(null);
  const [error, setError] = useState<ConflictReviewError | null>(null);
  conflictsRef.current = conflicts;

  const refresh = useCallback(async (): Promise<void> => {
    const currentHouseholdId = householdId?.trim();
    const generation = ++generationRef.current;
    if (!currentHouseholdId) {
      setConflicts([]);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const repository = await dependencies.getRepository();
      const reviewedMutations = await repository.listRequiresReview(currentHouseholdId);
      if (generationRef.current === generation) {
        setConflicts(reviewedMutations);
      }
    } catch (loadError) {
      if (generationRef.current === generation) {
        setConflicts([]);
        setError("load_failed");
        errorHandlerRef.current?.(loadError);
      }
    } finally {
      if (generationRef.current === generation) {
        setLoading(false);
      }
    }
  }, [dependencies, householdId]);

  useEffect(() => {
    void refresh();
    return () => {
      generationRef.current += 1;
    };
  }, [refresh]);

  const keepFamilyVersion = useCallback(
    async (mutationId: string): Promise<boolean> => {
      const currentHouseholdId = householdId?.trim();
      if (!currentHouseholdId || resolvingRef.current) {
        return false;
      }

      const mutation = conflictsRef.current.find(
        (conflict) =>
          conflict.mutationId === mutationId &&
          conflict.householdId === currentHouseholdId,
      );
      if (mutation === undefined) {
        return false;
      }

      const generation = generationRef.current;
      resolvingRef.current = true;
      setResolvingMutationId(mutationId);
      setError(null);
      try {
        const repository = await dependencies.getRepository();
        await refreshShoppingSessionGroceryQueries(
          queryClient,
          currentHouseholdId,
          mutation.shoppingSessionId,
        );
        await repository.resolveReviewByKeepingServerVersion(
          currentHouseholdId,
          mutationId,
        );
        if (generationRef.current === generation) {
          setConflicts((current) =>
            current.filter((conflict) => conflict.mutationId !== mutationId),
          );
        }
        return true;
      } catch (resolveError) {
        if (generationRef.current === generation) {
          setError("resolve_failed");
          errorHandlerRef.current?.(resolveError);
        }
        return false;
      } finally {
        resolvingRef.current = false;
        if (generationRef.current === generation) {
          setResolvingMutationId(null);
        }
      }
    },
    [dependencies, householdId, queryClient],
  );

  return {
    conflicts,
    loading,
    resolvingMutationId,
    error,
    refresh,
    keepFamilyVersion,
  };
}
