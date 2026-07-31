import { StyleSheet, Text, View } from "react-native";

import { RealtimeCloseOutcome } from "../services/realtime";

export type RealtimeStatusNoticeProps = {
  outcome: RealtimeCloseOutcome | null;
};

export function RealtimeStatusNotice({ outcome }: RealtimeStatusNoticeProps) {
  if (outcome === null || outcome.kind === "normal") {
    return null;
  }

  const isTemporary = outcome.retryable;

  return (
    <View
      accessible
      accessibilityLabel={outcome.message}
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
        {outcome.message}
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
