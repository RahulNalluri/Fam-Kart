import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { RealtimeCloseKind, RealtimeCloseOutcome } from "../services/realtime";

export type RealtimeStatusNoticeProps = {
  outcome: RealtimeCloseOutcome | null;
};

const realtimeMessageKeys = {
  authentication_required: "realtime.authenticationRequired",
  connection_interrupted: "realtime.connectionInterrupted",
  household_unavailable: "realtime.householdUnavailable",
  normal: "realtime.normal",
  service_unavailable: "realtime.serviceUnavailable",
} as const satisfies Record<RealtimeCloseKind, string>;

export function RealtimeStatusNotice({ outcome }: RealtimeStatusNoticeProps) {
  const { t } = useTranslation();

  if (outcome === null || outcome.kind === "normal") {
    return null;
  }

  const isTemporary = outcome.retryable;
  const message = t(realtimeMessageKeys[outcome.kind]);

  return (
    <View
      accessible
      accessibilityLabel={message}
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
      style={[
        styles.notice,
        isTemporary ? styles.temporaryNotice : styles.actionRequiredNotice,
      ]}
    >
      <Text
        style={[
          styles.message,
          isTemporary ? styles.temporaryMessage : styles.actionRequiredMessage,
        ]}
      >
        {message}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  actionRequiredMessage: {
    color: "#7A271A",
  },
  actionRequiredNotice: {
    backgroundColor: "#FEF3F2",
    borderColor: "#D92D20",
  },
  message: {
    fontSize: 15,
    fontWeight: "600",
    lineHeight: 22,
  },
  notice: {
    borderLeftWidth: 4,
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
    width: "100%",
  },
  temporaryMessage: {
    color: "#713B12",
  },
  temporaryNotice: {
    backgroundColor: "#FFFAEB",
    borderColor: "#DC6803",
  },
});
