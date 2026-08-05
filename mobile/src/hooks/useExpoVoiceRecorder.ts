import {
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";

import { expoMicrophonePermissionGateway } from "../features/voice/expoMicrophonePermissions";
import {
  VoiceAudioModeGateway,
  VoiceRecorderController,
  VoiceRecording,
  useVoiceRecorder,
} from "./useVoiceRecorder";

const expoVoiceAudioModeGateway: VoiceAudioModeGateway = {
  enableRecording: () =>
    setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    }),
  disableRecording: () => setAudioModeAsync({ allowsRecording: false }),
};

export function useExpoVoiceRecorder(
  onRecordingReady?: (recording: VoiceRecording) => void,
): VoiceRecorderController {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 200);

  return useVoiceRecorder({
    recorder,
    recorderState,
    permissionGateway: expoMicrophonePermissionGateway,
    audioModeGateway: expoVoiceAudioModeGateway,
    onRecordingReady,
  });
}
