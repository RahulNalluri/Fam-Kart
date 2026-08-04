import { VOICE_INPUT_REQUIREMENTS } from "../src/features/voice/requirements";

describe("voice input requirements", () => {
  it("requires foreground microphone access", () => {
    expect(VOICE_INPUT_REQUIREMENTS.requiresMicrophonePermission).toBe(true);
    expect(VOICE_INPUT_REQUIREMENTS.allowsBackgroundRecording).toBe(false);
  });

  it("uses bounded recording limits", () => {
    expect(VOICE_INPUT_REQUIREMENTS.maximumDurationSeconds).toBe(30);
    expect(VOICE_INPUT_REQUIREMENTS.maximumFileSizeBytes).toBe(5 * 1024 * 1024);
  });

  it("cannot be changed at runtime", () => {
    expect(Object.isFrozen(VOICE_INPUT_REQUIREMENTS)).toBe(true);
  });
});
