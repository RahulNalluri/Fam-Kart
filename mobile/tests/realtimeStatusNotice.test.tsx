import { render, screen } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { RealtimeStatusNotice } from "../src/components/RealtimeStatusNotice";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";
import { RealtimeCloseDetails, classifyRealtimeClose } from "../src/services/realtime";

function renderClose(
  details: RealtimeCloseDetails,
  language: SupportedLanguage = "en",
) {
  return render(
    <I18nextProvider i18n={createAppI18n(language)}>
      <RealtimeStatusNotice outcome={classifyRealtimeClose(details)} />
    </I18nextProvider>,
  );
}

describe("RealtimeStatusNotice", () => {
  it.each([
    [4401, "Your session has expired. Please sign in again."],
    [4404, "This household is no longer available to your account."],
    [1013, "Real-time updates are temporarily unavailable. Reconnecting."],
    [1006, "The real-time connection was interrupted. Reconnecting."],
  ])("shows readable text for close code %s", (code, expectedMessage) => {
    renderClose({ code: code as number, reason: "Technical server reason." });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByLabelText(expectedMessage as string)).toBeTruthy();
    expect(screen.getByText(expectedMessage as string)).toBeTruthy();
    expect(screen.queryByText(String(code))).toBeNull();
    expect(screen.queryByText("Technical server reason.")).toBeNull();
  });

  it("renders nothing for a normal closure", () => {
    const { toJSON } = renderClose({ code: 1000, reason: "Normal closure." });

    expect(toJSON()).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders nothing when no close outcome exists", () => {
    const { toJSON } = render(
      <I18nextProvider i18n={createAppI18n("en")}>
        <RealtimeStatusNotice outcome={null} />
      </I18nextProvider>,
    );

    expect(toJSON()).toBeNull();
  });

  it("shows Telugu text when Telugu is active", () => {
    renderClose({ code: 4401, reason: "Authentication required." }, "te");

    const message = "మీ సెషన్ గడువు ముగిసింది. దయచేసి మళ్లీ సైన్ ఇన్ చేయండి.";
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByLabelText(message)).toBeTruthy();
    expect(screen.getByText(message)).toBeTruthy();
  });
});
