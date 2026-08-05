import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AppStateStatus } from "react-native";

import { MicrophonePermissionGateway } from "../src/features/voice/microphonePermissions";
import {
  VoiceAudioModeGateway,
  VoiceRecorderAppState,
  VoiceRecorderNative,
  VoiceRecorderNativeState,
  useVoiceRecorder,
} from "../src/hooks/useVoiceRecorder";

class FakeAppState implements VoiceRecorderAppState {
  private readonly listeners = new Set<(state: AppStateStatus) => void>();

  constructor(public currentState: AppStateStatus = "active") {}

  addEventListener(
    type: "change",
    listener: (state: AppStateStatus) => void,
  ): { remove(): void } {
    this.listeners.add(listener);
    return { remove: () => this.listeners.delete(listener) };
  }

  transitionTo(state: AppStateStatus): void {
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }
}

function permissionGateway(
  granted = true,
  canAskAgain = true,
): jest.Mocked<MicrophonePermissionGateway> {
  return {
    get: jest.fn().mockResolvedValue({ granted, canAskAgain }),
    request: jest.fn().mockResolvedValue({ granted, canAskAgain }),
  };
}

function buildHarness(permission = permissionGateway()) {
  let nativeState: VoiceRecorderNativeState = {
    isRecording: false,
    durationMillis: 0,
    url: null,
  };
  const recorder: jest.Mocked<VoiceRecorderNative> = {
    uri: null,
    prepareToRecordAsync: jest.fn().mockResolvedValue(undefined),
    record: jest.fn(),
    stop: jest.fn().mockResolvedValue(undefined),
    getStatus: jest.fn(() => nativeState),
  };
  const audioModeGateway: jest.Mocked<VoiceAudioModeGateway> = {
    enableRecording: jest.fn().mockResolvedValue(undefined),
    disableRecording: jest.fn().mockResolvedValue(undefined),
  };
  const appState = new FakeAppState();
  const onRecordingReady = jest.fn();
  const view = renderHook(
    ({ recorderState }: { recorderState: VoiceRecorderNativeState }) =>
      useVoiceRecorder({
        recorder,
        recorderState,
        permissionGateway: permission,
        audioModeGateway,
        appState,
        onRecordingReady,
      }),
    { initialProps: { recorderState: nativeState } },
  );

  return {
    ...view,
    appState,
    audioModeGateway,
    onRecordingReady,
    permission,
    recorder,
    setNativeState(state: VoiceRecorderNativeState) {
      nativeState = state;
      view.rerender({ recorderState: state });
    },
  };
}

async function startRecording(harness: ReturnType<typeof buildHarness>) {
  await act(async () => {
    await harness.result.current.startRecording();
  });
}

describe("useVoiceRecorder", () => {
  it("requests permission and starts a 30-second foreground recording", async () => {
    const harness = buildHarness();

    await startRecording(harness);

    expect(harness.result.current.phase).toBe("recording");
    expect(harness.permission.get).toHaveBeenCalledTimes(1);
    expect(harness.audioModeGateway.enableRecording).toHaveBeenCalledTimes(1);
    expect(harness.recorder.prepareToRecordAsync).toHaveBeenCalledTimes(1);
    expect(harness.recorder.record).toHaveBeenCalledWith({ forDuration: 30 });
  });

  it("stops and delivers a bounded local recording", async () => {
    const harness = buildHarness();
    await startRecording(harness);
    harness.setNativeState({
      isRecording: true,
      durationMillis: 4_250,
      url: "file:///voice-command.m4a",
    });

    await act(async () => {
      await harness.result.current.stopRecording();
    });

    expect(harness.result.current.phase).toBe("recorded");
    expect(harness.result.current.recording).toEqual({
      uri: "file:///voice-command.m4a",
      durationMillis: 4_250,
    });
    expect(harness.audioModeGateway.disableRecording).toHaveBeenCalledTimes(1);
    expect(harness.onRecordingReady).toHaveBeenCalledWith(
      harness.result.current.recording,
    );
  });

  it("cancels without exposing a recording URI", async () => {
    const harness = buildHarness();
    await startRecording(harness);

    await act(async () => {
      await harness.result.current.cancelRecording();
    });

    expect(harness.result.current.phase).toBe("idle");
    expect(harness.result.current.recording).toBeNull();
    expect(harness.recorder.stop).toHaveBeenCalledTimes(1);
    expect(harness.onRecordingReady).not.toHaveBeenCalled();
  });

  it("cancels an active recording when the app leaves the foreground", async () => {
    const harness = buildHarness();
    await startRecording(harness);

    await act(async () => {
      harness.appState.transitionTo("background");
      await Promise.resolve();
    });

    expect(harness.result.current.phase).toBe("idle");
    expect(harness.recorder.stop).toHaveBeenCalledTimes(1);
    expect(harness.result.current.recording).toBeNull();
  });

  it("finalizes when Expo reaches the native duration limit", async () => {
    const harness = buildHarness();
    await startRecording(harness);
    act(() => {
      harness.setNativeState({
        isRecording: true,
        durationMillis: 29_800,
        url: null,
      });
    });
    act(() => {
      harness.setNativeState({
        isRecording: false,
        durationMillis: 30_100,
        url: "file:///automatic-stop.m4a",
      });
    });

    await waitFor(() => expect(harness.result.current.phase).toBe("recorded"));

    expect(harness.result.current.recording).toEqual({
      uri: "file:///automatic-stop.m4a",
      durationMillis: 30_000,
    });
    expect(harness.recorder.stop).not.toHaveBeenCalled();
  });

  it.each([
    [permissionGateway(false, true), "permission_denied"],
    [permissionGateway(false, false), "permission_blocked"],
  ] as const)("shows a controlled permission outcome", async (permission, error) => {
    const harness = buildHarness(permission);

    await startRecording(harness);

    expect(harness.result.current.phase).toBe("error");
    expect(harness.result.current.error).toBe(error);
    expect(harness.audioModeGateway.enableRecording).not.toHaveBeenCalled();
    expect(harness.recorder.record).not.toHaveBeenCalled();
  });

  it("releases audio mode after a native preparation failure", async () => {
    const harness = buildHarness();
    harness.recorder.prepareToRecordAsync.mockRejectedValueOnce(
      new Error("Microphone unavailable"),
    );

    await startRecording(harness);

    expect(harness.result.current.phase).toBe("error");
    expect(harness.result.current.error).toBe("recording_failed");
    expect(harness.audioModeGateway.disableRecording).toHaveBeenCalledTimes(1);
  });
});
