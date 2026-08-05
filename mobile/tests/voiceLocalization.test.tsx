import { act, render, screen } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { VoiceConfirmationScreen } from "../src/components/VoiceConfirmationScreen";
import { VoiceRecorderView } from "../src/components/VoiceRecorder";
import { VoiceConfirmationItem } from "../src/features/voice/confirmation";
import { VoiceRecorderController } from "../src/hooks/useVoiceRecorder";
import { createAppI18n } from "../src/locales/i18n";

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

jest.mock("../src/hooks/useExpoVoiceRecorder", () => ({
  useExpoVoiceRecorder: jest.fn(),
}));

const recorderController: VoiceRecorderController = {
  phase: "idle",
  error: null,
  durationMillis: 0,
  recording: null,
  startRecording: jest.fn().mockResolvedValue(undefined),
  stopRecording: jest.fn().mockResolvedValue(undefined),
  cancelRecording: jest.fn().mockResolvedValue(undefined),
  resetRecording: jest.fn(),
};

const item: VoiceConfirmationItem = {
  id: "family-milk",
  name: "Maa paalu",
  canonicalKey: "milk",
  quantity: "2",
  unit: "packet",
};

describe("English and Telugu voice localization", () => {
  it("updates the complete visible voice workflow when language changes", async () => {
    const instance = createAppI18n("en");
    render(
      <I18nextProvider i18n={instance}>
        <VoiceRecorderView controller={recorderController} />
        <VoiceConfirmationScreen
          initialItems={[item]}
          onCancel={jest.fn()}
          onConfirm={jest.fn()}
          onRecordAgain={jest.fn()}
          submitErrorCode="network_unavailable"
          transcript="Maa paalu rendu packets"
        />
      </I18nextProvider>,
    );

    expect(screen.getByText("Ready to record")).toBeTruthy();
    expect(screen.getByText("Review voice items")).toBeTruthy();
    expect(
      screen.getByText(
        "Could not connect. Check your internet connection and try again.",
      ),
    ).toBeTruthy();

    await act(async () => {
      await instance.changeLanguage("te");
    });

    expect(screen.getByText("రికార్డ్ చేయడానికి సిద్ధంగా ఉంది")).toBeTruthy();
    expect(screen.getByText("వాయిస్ సరుకులను తనిఖీ చేయండి")).toBeTruthy();
    expect(
      screen.getByText(
        "కనెక్ట్ కాలేకపోయాము. మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.",
      ),
    ).toBeTruthy();
  });

  it("keeps family speech and grocery names unchanged across languages", async () => {
    const instance = createAppI18n("en");
    render(
      <I18nextProvider i18n={instance}>
        <VoiceConfirmationScreen
          initialItems={[item]}
          onCancel={jest.fn()}
          onConfirm={jest.fn()}
          onRecordAgain={jest.fn()}
          transcript="Maa paalu rendu packets"
        />
      </I18nextProvider>,
    );

    await act(async () => {
      await instance.changeLanguage("te");
    });

    expect(screen.getByText("Maa paalu rendu packets")).toBeTruthy();
    expect(screen.getByDisplayValue("Maa paalu")).toBeTruthy();
  });

  it.each([
    [
      "network_unavailable",
      "Could not connect. Check your internet connection and try again.",
    ],
    ["session_expired", "Your session has expired. Please sign in again."],
    ["household_unavailable", "This household is no longer available to your account."],
    ["save_failed", "The grocery items could not be added. Please try again."],
  ] as const)("localizes controlled %s errors", (submitErrorCode, expected) => {
    render(
      <I18nextProvider i18n={createAppI18n("en")}>
        <VoiceConfirmationScreen
          initialItems={[item]}
          onCancel={jest.fn()}
          onConfirm={jest.fn()}
          onRecordAgain={jest.fn()}
          submitErrorCode={submitErrorCode}
          transcript="Maa paalu rendu packets"
        />
      </I18nextProvider>,
    );

    expect(screen.getByRole("alert", { name: expected })).toBeTruthy();
  });

  it.each([
    [
      "network_unavailable",
      "కనెక్ట్ కాలేకపోయాము. మీ ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి మళ్లీ ప్రయత్నించండి.",
    ],
    ["session_expired", "మీ సెషన్ గడువు ముగిసింది. దయచేసి మళ్లీ సైన్ ఇన్ చేయండి."],
    ["household_unavailable", "ఈ కుటుంబం ఇకపై మీ ఖాతాకు అందుబాటులో లేదు."],
    ["save_failed", "సరుకులను జోడించలేకపోయాము. దయచేసి మళ్లీ ప్రయత్నించండి."],
  ] as const)(
    "localizes controlled %s errors in Telugu",
    (submitErrorCode, expected) => {
      render(
        <I18nextProvider i18n={createAppI18n("te")}>
          <VoiceConfirmationScreen
            initialItems={[item]}
            onCancel={jest.fn()}
            onConfirm={jest.fn()}
            onRecordAgain={jest.fn()}
            submitErrorCode={submitErrorCode}
            transcript="Maa paalu rendu packets"
          />
        </I18nextProvider>,
      );

      expect(screen.getByRole("alert", { name: expected })).toBeTruthy();
    },
  );
});
