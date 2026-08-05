import { Ionicons } from "@expo/vector-icons";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { VOICE_INPUT_REQUIREMENTS } from "../features/voice/requirements";
import { useExpoVoiceRecorder } from "../hooks/useExpoVoiceRecorder";
import {
  VoiceRecorderController,
  VoiceRecorderError,
  VoiceRecorderPhase,
  VoiceRecording,
} from "../hooks/useVoiceRecorder";

export type VoiceRecorderProps = {
  onRecordingReady?: (recording: VoiceRecording) => void;
};

export type VoiceRecorderViewProps = {
  controller: VoiceRecorderController;
  openSettings?: () => Promise<void>;
};

const phaseMessageKeys = {
  idle: "voice.recorder.idle",
  preparing: "voice.recorder.preparing",
  recorded: "voice.recorder.ready",
  recording: "voice.recorder.recording",
  requesting_permission: "voice.recorder.requestingPermission",
  stopping: "voice.recorder.stopping",
} as const satisfies Record<Exclude<VoiceRecorderPhase, "error">, string>;

const errorMessageKeys = {
  permission_blocked: "voice.permission.blocked",
  permission_denied: "voice.permission.denied",
  recording_failed: "voice.recorder.failed",
} as const satisfies Record<VoiceRecorderError, string>;

function formatSeconds(durationMillis: number): number {
  return Math.min(
    Math.floor(durationMillis / 1000),
    VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds,
  );
}

export function VoiceRecorderView({
  controller,
  openSettings = Linking.openSettings,
}: VoiceRecorderViewProps) {
  const { t } = useTranslation();
  const isRecording = controller.phase === "recording";
  const isBusy = ["requesting_permission", "preparing", "stopping"].includes(
    controller.phase,
  );
  const statusMessage = controller.error
    ? t(errorMessageKeys[controller.error])
    : t(phaseMessageKeys[controller.phase as Exclude<VoiceRecorderPhase, "error">]);

  return (
    <View accessibilityLiveRegion="polite" style={styles.container}>
      <Text accessibilityRole="header" style={styles.title}>
        {t("voice.recorder.title")}
      </Text>
      <Text
        accessibilityRole={controller.error ? "alert" : undefined}
        style={styles.status}
      >
        {statusMessage}
      </Text>

      {isRecording ? (
        <Text
          accessibilityLabel={t("voice.recorder.durationAccessibility", {
            maximum: VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds,
            seconds: formatSeconds(controller.durationMillis),
          })}
          style={styles.timer}
        >
          {formatSeconds(controller.durationMillis)} /{" "}
          {VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds}
        </Text>
      ) : null}

      <View style={styles.actions}>
        {controller.phase === "idle" || controller.error ? (
          <Pressable
            accessibilityLabel={t("voice.recorder.start")}
            accessibilityRole="button"
            disabled={isBusy}
            onPress={() => void controller.startRecording()}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed ? styles.pressedButton : null,
            ]}
          >
            <Ionicons color="#FFFFFF" name="mic" size={22} />
            <Text style={styles.primaryButtonText}>{t("voice.recorder.start")}</Text>
          </Pressable>
        ) : null}

        {isRecording ? (
          <>
            <Pressable
              accessibilityLabel={t("voice.recorder.stop")}
              accessibilityRole="button"
              onPress={() => void controller.stopRecording()}
              style={({ pressed }) => [
                styles.stopButton,
                pressed ? styles.pressedButton : null,
              ]}
            >
              <Ionicons color="#FFFFFF" name="stop" size={20} />
              <Text style={styles.stopButtonText}>{t("voice.recorder.stop")}</Text>
            </Pressable>
            <Pressable
              accessibilityLabel={t("voice.recorder.cancel")}
              accessibilityRole="button"
              onPress={() => void controller.cancelRecording()}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed ? styles.pressedButton : null,
              ]}
            >
              <Ionicons color="#33443A" name="close" size={22} />
              <Text style={styles.secondaryButtonText}>
                {t("voice.recorder.cancel")}
              </Text>
            </Pressable>
          </>
        ) : null}

        {controller.phase === "recorded" ? (
          <Pressable
            accessibilityLabel={t("voice.recorder.recordAgain")}
            accessibilityRole="button"
            onPress={controller.resetRecording}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed ? styles.pressedButton : null,
            ]}
          >
            <Ionicons color="#33443A" name="refresh" size={20} />
            <Text style={styles.secondaryButtonText}>
              {t("voice.recorder.recordAgain")}
            </Text>
          </Pressable>
        ) : null}

        {controller.error === "permission_blocked" ? (
          <Pressable
            accessibilityLabel={t("voice.permission.openSettings")}
            accessibilityRole="button"
            onPress={() => void openSettings()}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed ? styles.pressedButton : null,
            ]}
          >
            <Ionicons color="#33443A" name="settings-outline" size={20} />
            <Text style={styles.secondaryButtonText}>
              {t("voice.permission.openSettings")}
            </Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

export function VoiceRecorder({ onRecordingReady }: VoiceRecorderProps) {
  const controller = useExpoVoiceRecorder(onRecordingReady);
  return <VoiceRecorderView controller={controller} />;
}

const styles = StyleSheet.create({
  actions: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    minHeight: 48,
  },
  container: {
    gap: 12,
    width: "100%",
  },
  pressedButton: {
    opacity: 0.72,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#176B45",
    borderRadius: 6,
    flexDirection: "row",
    gap: 8,
    height: 48,
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderColor: "#A8B8AE",
    borderRadius: 6,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    height: 48,
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  secondaryButtonText: {
    color: "#33443A",
    fontSize: 15,
    fontWeight: "700",
  },
  status: {
    color: "#46584E",
    fontSize: 15,
    lineHeight: 22,
  },
  stopButton: {
    alignItems: "center",
    backgroundColor: "#B42318",
    borderRadius: 6,
    flexDirection: "row",
    gap: 7,
    height: 48,
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  stopButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700",
  },
  timer: {
    color: "#B42318",
    fontSize: 24,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  title: {
    color: "#173B2A",
    fontSize: 20,
    fontWeight: "800",
  },
});
