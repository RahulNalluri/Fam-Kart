import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, AppStateStatus } from "react-native";

import { VOICE_INPUT_REQUIREMENTS } from "../features/voice/requirements";
import {
  ensureMicrophonePermission,
  MicrophonePermissionGateway,
} from "../features/voice/microphonePermissions";

export type VoiceRecorderPhase =
  | "idle"
  | "requesting_permission"
  | "preparing"
  | "recording"
  | "stopping"
  | "recorded"
  | "error";

export type VoiceRecorderError =
  "permission_denied" | "permission_blocked" | "recording_failed";

export type VoiceRecording = Readonly<{
  uri: string;
  durationMillis: number;
}>;

export type VoiceRecorderNativeState = {
  isRecording: boolean;
  durationMillis: number;
  url: string | null;
};

export interface VoiceRecorderNative {
  readonly uri: string | null;
  prepareToRecordAsync(): Promise<void>;
  record(options: { forDuration: number }): void;
  stop(): Promise<void>;
  getStatus(): VoiceRecorderNativeState;
}

export interface VoiceAudioModeGateway {
  enableRecording(): Promise<void>;
  disableRecording(): Promise<void>;
}

export interface VoiceRecorderAppState {
  currentState: AppStateStatus;
  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void };
}

export type UseVoiceRecorderOptions = {
  recorder: VoiceRecorderNative;
  recorderState: VoiceRecorderNativeState;
  permissionGateway: MicrophonePermissionGateway;
  audioModeGateway: VoiceAudioModeGateway;
  appState?: VoiceRecorderAppState;
  onRecordingReady?: (recording: VoiceRecording) => void;
};

export type VoiceRecorderController = {
  phase: VoiceRecorderPhase;
  error: VoiceRecorderError | null;
  durationMillis: number;
  recording: VoiceRecording | null;
  startRecording(): Promise<void>;
  stopRecording(): Promise<void>;
  cancelRecording(): Promise<void>;
  resetRecording(): void;
};

const maximumDurationMillis = VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds * 1000;

export function useVoiceRecorder({
  recorder,
  recorderState,
  permissionGateway,
  audioModeGateway,
  appState = AppState,
  onRecordingReady,
}: UseVoiceRecorderOptions): VoiceRecorderController {
  const [phase, setPhase] = useState<VoiceRecorderPhase>("idle");
  const [error, setError] = useState<VoiceRecorderError | null>(null);
  const [recording, setRecording] = useState<VoiceRecording | null>(null);
  const phaseRef = useRef<VoiceRecorderPhase>("idle");
  const operationInProgressRef = useRef(false);
  const observedNativeRecordingRef = useRef(false);

  const transition = useCallback((nextPhase: VoiceRecorderPhase) => {
    phaseRef.current = nextPhase;
    setPhase(nextPhase);
  }, []);

  const failRecording = useCallback(async () => {
    try {
      await audioModeGateway.disableRecording();
    } catch {
      // The original recording failure remains the useful UI outcome.
    }
    setRecording(null);
    setError("recording_failed");
    transition("error");
    operationInProgressRef.current = false;
  }, [audioModeGateway, transition]);

  const finalizeStoppedRecording = useCallback(async () => {
    try {
      await audioModeGateway.disableRecording();
      const status = recorder.getStatus();
      const uri = status.url ?? recorder.uri;
      if (!uri) {
        throw new Error("The native recorder returned no local URI.");
      }
      const completedRecording = Object.freeze({
        uri,
        durationMillis: Math.min(status.durationMillis, maximumDurationMillis),
      });
      setRecording(completedRecording);
      setError(null);
      transition("recorded");
      onRecordingReady?.(completedRecording);
      operationInProgressRef.current = false;
    } catch {
      await failRecording();
    }
  }, [audioModeGateway, failRecording, onRecordingReady, recorder, transition]);

  const startRecording = useCallback(async () => {
    if (operationInProgressRef.current || phaseRef.current === "recording") {
      return;
    }

    operationInProgressRef.current = true;
    setRecording(null);
    setError(null);
    transition("requesting_permission");

    try {
      const permission = await ensureMicrophonePermission(permissionGateway);
      if (permission !== "granted") {
        setError(permission === "blocked" ? "permission_blocked" : "permission_denied");
        transition("error");
        operationInProgressRef.current = false;
        return;
      }
      if (appState.currentState !== "active") {
        throw new Error("Recording can start only while the app is active.");
      }

      transition("preparing");
      await audioModeGateway.enableRecording();
      await recorder.prepareToRecordAsync();
      if (appState.currentState !== "active") {
        throw new Error("The app left the foreground while preparing audio.");
      }

      observedNativeRecordingRef.current = false;
      recorder.record({
        forDuration: VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds,
      });
      transition("recording");
      operationInProgressRef.current = false;
    } catch {
      await failRecording();
    }
  }, [
    appState,
    audioModeGateway,
    failRecording,
    permissionGateway,
    recorder,
    transition,
  ]);

  const stopRecording = useCallback(async () => {
    if (operationInProgressRef.current || phaseRef.current !== "recording") {
      return;
    }

    operationInProgressRef.current = true;
    transition("stopping");
    try {
      await recorder.stop();
      await finalizeStoppedRecording();
    } catch {
      await failRecording();
    }
  }, [failRecording, finalizeStoppedRecording, recorder, transition]);

  const cancelRecording = useCallback(async () => {
    if (operationInProgressRef.current || phaseRef.current !== "recording") {
      return;
    }

    operationInProgressRef.current = true;
    transition("stopping");
    try {
      await recorder.stop();
      await audioModeGateway.disableRecording();
      setRecording(null);
      setError(null);
      transition("idle");
      operationInProgressRef.current = false;
    } catch {
      await failRecording();
    }
  }, [audioModeGateway, failRecording, recorder, transition]);

  const resetRecording = useCallback(() => {
    if (operationInProgressRef.current || phaseRef.current === "recording") {
      return;
    }
    setRecording(null);
    setError(null);
    transition("idle");
  }, [transition]);

  useEffect(() => {
    if (phase !== "recording") {
      return;
    }
    if (recorderState.isRecording) {
      observedNativeRecordingRef.current = true;
      return;
    }
    if (observedNativeRecordingRef.current && !operationInProgressRef.current) {
      operationInProgressRef.current = true;
      transition("stopping");
      void finalizeStoppedRecording();
    }
  }, [finalizeStoppedRecording, phase, recorderState.isRecording, transition]);

  useEffect(() => {
    const subscription = appState.addEventListener("change", (nextState) => {
      if (nextState !== "active" && phaseRef.current === "recording") {
        void cancelRecording();
      }
    });
    return () => subscription.remove();
  }, [appState, cancelRecording]);

  useEffect(
    () => () => {
      if (phaseRef.current === "recording") {
        void recorder.stop().finally(() => audioModeGateway.disableRecording());
      }
    },
    [audioModeGateway, recorder],
  );

  return {
    phase,
    error,
    durationMillis:
      phase === "recording"
        ? Math.min(recorderState.durationMillis, maximumDurationMillis)
        : (recording?.durationMillis ?? 0),
    recording,
    startRecording,
    stopRecording,
    cancelRecording,
    resetRecording,
  };
}
