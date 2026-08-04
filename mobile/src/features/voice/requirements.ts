export const VOICE_INPUT_REQUIREMENTS = Object.freeze({
  requiresMicrophonePermission: true,
  allowsBackgroundRecording: false,
  maximumDurationSeconds: 30,
  maximumFileSizeBytes: 5 * 1024 * 1024,
} as const);
