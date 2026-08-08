import { Ionicons } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { QueuedOfflineMutation } from "../features/offline/localMutationQueueRepository";
import { OfflineMutationOperation } from "../features/offline/synchronizationPolicy";
import { ConflictReviewError } from "../hooks/useGroceryConflictReview";

export type ConflictReviewPanelProps = Readonly<{
  conflicts: readonly QueuedOfflineMutation[];
  loading: boolean;
  resolvingMutationId: string | null;
  error: ConflictReviewError | null;
  onKeepFamilyVersion: (mutationId: string) => void | Promise<unknown>;
  onReviewChange: (mutation: QueuedOfflineMutation) => void;
  getItemName?: (mutation: QueuedOfflineMutation) => string | null | undefined;
}>;

const operationKeys = {
  add: "offline.conflicts.operations.add",
  edit: "offline.conflicts.operations.edit",
  complete: "offline.conflicts.operations.complete",
  reopen: "offline.conflicts.operations.reopen",
  delete: "offline.conflicts.operations.delete",
} as const satisfies Record<OfflineMutationOperation, string>;

function safePayloadText(value: unknown, maximumLength: number): string | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value).slice(0, maximumLength);
  }
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized ? normalized.slice(0, maximumLength) : null;
}

function reasonKey(errorCode: string | null): string {
  if (errorCode === "server_conflict") {
    return "offline.conflicts.reasons.serverConflict";
  }
  if (errorCode === "invalid_mutation") {
    return "offline.conflicts.reasons.invalidMutation";
  }
  return "offline.conflicts.reasons.reviewRequired";
}

export function ConflictReviewPanel({
  conflicts,
  loading,
  resolvingMutationId,
  error,
  onKeepFamilyVersion,
  onReviewChange,
  getItemName,
}: ConflictReviewPanelProps) {
  const { t } = useTranslation();

  return (
    <View style={styles.panel}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text accessibilityRole="header" style={styles.title}>
            {t("offline.conflicts.title")}
          </Text>
          <Text style={styles.count}>
            {t("offline.conflicts.count", { count: conflicts.length })}
          </Text>
        </View>
        {loading ? (
          <ActivityIndicator
            accessibilityLabel={t("offline.conflicts.loading")}
            color="#176B45"
          />
        ) : null}
      </View>

      {error ? (
        <Text
          accessibilityLiveRegion="polite"
          accessibilityRole="alert"
          style={styles.error}
        >
          {t(
            error === "load_failed"
              ? "offline.conflicts.loadFailed"
              : "offline.conflicts.resolveFailed",
          )}
        </Text>
      ) : null}

      {loading && conflicts.length === 0 ? (
        <Text style={styles.stateText}>{t("offline.conflicts.loading")}</Text>
      ) : null}

      {!loading && error === null && conflicts.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons color="#557066" name="checkmark-circle-outline" size={24} />
          <Text style={styles.stateText}>{t("offline.conflicts.empty")}</Text>
        </View>
      ) : null}

      <View style={styles.list}>
        {conflicts.map((conflict) => {
          const itemName =
            safePayloadText(getItemName?.(conflict), 160) ??
            safePayloadText(conflict.payload.name, 160) ??
            t("offline.conflicts.itemFallback");
          const operation = t(operationKeys[conflict.operation]);
          const summary = t("offline.conflicts.summary", { operation, item: itemName });
          const quantity = safePayloadText(conflict.payload.quantity, 32);
          const unit = safePayloadText(conflict.payload.unit, 32);
          const resolving = resolvingMutationId === conflict.mutationId;
          const actionsDisabled = resolvingMutationId !== null;

          return (
            <View key={conflict.mutationId} style={styles.card}>
              <View style={styles.cardHeader}>
                <Ionicons color="#9A5B13" name="git-compare-outline" size={20} />
                <Text accessibilityLabel={summary} style={styles.summary}>
                  {summary}
                </Text>
              </View>
              <Text style={styles.reason}>{t(reasonKey(conflict.lastErrorCode))}</Text>
              {quantity || unit ? (
                <View style={styles.details}>
                  {quantity ? (
                    <Text style={styles.detailText}>
                      {t("offline.conflicts.quantity", { value: quantity })}
                    </Text>
                  ) : null}
                  {unit ? (
                    <Text style={styles.detailText}>
                      {t("offline.conflicts.unit", { value: unit })}
                    </Text>
                  ) : null}
                </View>
              ) : null}
              <View style={styles.actions}>
                <Pressable
                  accessibilityRole="button"
                  disabled={actionsDisabled}
                  onPress={() => onReviewChange(conflict)}
                  style={({ pressed }) => [
                    styles.secondaryButton,
                    pressed && !actionsDisabled ? styles.pressed : null,
                    actionsDisabled ? styles.disabledButton : null,
                  ]}
                >
                  <Ionicons color="#294C3A" name="create-outline" size={18} />
                  <Text style={styles.secondaryButtonText}>
                    {t("offline.conflicts.reviewChange")}
                  </Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  disabled={actionsDisabled}
                  onPress={() => void onKeepFamilyVersion(conflict.mutationId)}
                  style={({ pressed }) => [
                    styles.primaryButton,
                    pressed && !actionsDisabled ? styles.pressed : null,
                    actionsDisabled ? styles.disabledButton : null,
                  ]}
                >
                  {resolving ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Ionicons color="#FFFFFF" name="people-outline" size={18} />
                  )}
                  <Text style={styles.primaryButtonText}>
                    {t(
                      resolving
                        ? "offline.conflicts.resolving"
                        : "offline.conflicts.keepFamilyVersion",
                    )}
                  </Text>
                </Pressable>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E1D3BE",
    borderRadius: 6,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  cardHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  count: {
    color: "#65756C",
    fontSize: 13,
  },
  detailText: {
    color: "#4A5E53",
    fontSize: 13,
  },
  details: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  disabledButton: {
    opacity: 0.55,
  },
  emptyState: {
    alignItems: "center",
    backgroundColor: "#F4F7F5",
    borderRadius: 6,
    flexDirection: "row",
    gap: 8,
    padding: 14,
  },
  error: {
    backgroundColor: "#FFF2F0",
    borderLeftColor: "#B42318",
    borderLeftWidth: 4,
    color: "#8A1C13",
    fontSize: 14,
    lineHeight: 20,
    padding: 12,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 42,
  },
  headerText: {
    flex: 1,
    gap: 2,
  },
  list: {
    gap: 10,
  },
  panel: {
    gap: 12,
    width: "100%",
  },
  pressed: {
    opacity: 0.72,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#176B45",
    borderRadius: 6,
    flexDirection: "row",
    gap: 7,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    flexShrink: 1,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
  reason: {
    color: "#6E4D20",
    fontSize: 14,
    lineHeight: 20,
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderColor: "#8FA499",
    borderRadius: 6,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  secondaryButtonText: {
    color: "#294C3A",
    flexShrink: 1,
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center",
  },
  stateText: {
    color: "#52635A",
    flexShrink: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  summary: {
    color: "#2D3F35",
    flex: 1,
    fontSize: 16,
    fontWeight: "800",
    lineHeight: 22,
  },
  title: {
    color: "#173B2A",
    fontSize: 20,
    fontWeight: "800",
  },
});
