import { fireEvent, render, screen } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { VoiceRecorderView } from "../src/components/VoiceRecorder";
import { VoiceRecorderController } from "../src/hooks/useVoiceRecorder";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";

jest.mock("../src/hooks/useExpoVoiceRecorder", () => ({
  useExpoVoiceRecorder: jest.fn(),
}));

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

function controller(
  overrides: Partial<VoiceRecorderController> = {},
): VoiceRecorderController {
  return {
    phase: "idle",
    error: null,
    durationMillis: 0,
    recording: null,
    startRecording: jest.fn().mockResolvedValue(undefined),
    stopRecording: jest.fn().mockResolvedValue(undefined),
    cancelRecording: jest.fn().mockResolvedValue(undefined),
    resetRecording: jest.fn(),
    ...overrides,
  };
}

function renderRecorder(
  recorderController: VoiceRecorderController,
  language: SupportedLanguage = "en",
  openSettings = jest.fn().mockResolvedValue(undefined),
) {
  return {
    ...render(
      <I18nextProvider i18n={createAppI18n(language)}>
        <VoiceRecorderView
          controller={recorderController}
          openSettings={openSettings}
        />
      </I18nextProvider>,
    ),
    openSettings,
  };
}

describe("VoiceRecorderView", () => {
  it("starts recording from an accessible microphone action", () => {
    const recorderController = controller();
    renderRecorder(recorderController);

    fireEvent.press(screen.getByRole("button", { name: "Start recording" }));

    expect(recorderController.startRecording).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Ready to record")).toBeTruthy();
  });

  it("shows stable stop and cancel actions with elapsed time", () => {
    const recorderController = controller({
      phase: "recording",
      durationMillis: 12_800,
    });
    renderRecorder(recorderController);

    expect(screen.getByText("12 / 30")).toBeTruthy();
    expect(screen.getByLabelText("Recorded 12 of 30 allowed seconds")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Stop recording" }));
    fireEvent.press(screen.getByRole("button", { name: "Cancel recording" }));

    expect(recorderController.stopRecording).toHaveBeenCalledTimes(1);
    expect(recorderController.cancelRecording).toHaveBeenCalledTimes(1);
  });

  it("opens settings after microphone permission is blocked", () => {
    const recorderController = controller({
      phase: "error",
      error: "permission_blocked",
    });
    const { openSettings } = renderRecorder(recorderController);

    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Open settings" }));

    expect(openSettings).toHaveBeenCalledTimes(1);
  });

  it("allows a completed local recording to be discarded and recorded again", () => {
    const recorderController = controller({
      phase: "recorded",
      durationMillis: 4_000,
      recording: { uri: "file:///voice.m4a", durationMillis: 4_000 },
    });
    renderRecorder(recorderController);

    expect(screen.getByText("Recording ready")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Record again" }));

    expect(recorderController.resetRecording).toHaveBeenCalledTimes(1);
  });

  it("renders Telugu recording controls", () => {
    const recorderController = controller();
    renderRecorder(recorderController, "te");

    expect(screen.getByText("వాయిస్ కమాండ్")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "రికార్డింగ్ ప్రారంభించండి" }),
    ).toBeTruthy();
  });
});
