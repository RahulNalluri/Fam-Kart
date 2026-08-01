import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { LanguageSwitcher } from "../src/components/LanguageSwitcher";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";

function renderSwitcher(language: SupportedLanguage = "en") {
  const i18n = createAppI18n(language);
  const view = render(
    <I18nextProvider i18n={i18n}>
      <LanguageSwitcher />
    </I18nextProvider>,
  );

  return { ...view, i18n };
}

describe("LanguageSwitcher", () => {
  it("shows both options with the active language selected", () => {
    renderSwitcher("en");

    expect(screen.getByText("Language")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "English" }).props.accessibilityState,
    ).toMatchObject({ selected: true });
    expect(
      screen.getByRole("button", { name: "తెలుగు" }).props.accessibilityState,
    ).toMatchObject({ selected: false });
  });

  it("switches to Telugu and updates the selector text", async () => {
    const { i18n } = renderSwitcher("en");

    fireEvent.press(screen.getByRole("button", { name: "తెలుగు" }));

    await waitFor(() => {
      expect(i18n.language).toBe("te");
      expect(screen.getByText("భాష")).toBeTruthy();
      expect(
        screen.getByRole("button", { name: "తెలుగు" }).props.accessibilityState,
      ).toMatchObject({ selected: true });
    });
  });

  it("switches back to English", async () => {
    const { i18n } = renderSwitcher("te");

    fireEvent.press(screen.getByRole("button", { name: "English" }));

    await waitFor(() => {
      expect(i18n.language).toBe("en");
      expect(screen.getByText("Language")).toBeTruthy();
    });
  });
});
