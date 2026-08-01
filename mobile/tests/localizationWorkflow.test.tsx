import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { i18n } from "i18next";
import { Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "../src/components/LanguageSwitcher";
import { LocalizationProvider } from "../src/components/LocalizationProvider";
import { RealtimeStatusNotice } from "../src/components/RealtimeStatusNotice";
import { useLanguagePreference } from "../src/hooks/useLanguagePreference";
import { createAppI18n } from "../src/locales/i18n";
import { LanguageStorage } from "../src/locales/languageStorage";
import { classifyRealtimeClose } from "../src/services/realtime";

class MemoryLanguageStorage implements LanguageStorage {
  readCount = 0;

  constructor(public value: string | null) {}

  async getItemAsync(): Promise<string | null> {
    this.readCount += 1;
    return this.value;
  }

  async setItemAsync(_key: string, value: string): Promise<void> {
    this.value = value;
  }
}

type LocalizationWorkflowHarnessProps = {
  instance: i18n;
  preferredLanguage?: string;
  storage: LanguageStorage;
};

function LocalizationWorkflowHarness({
  instance,
  preferredLanguage,
  storage,
}: LocalizationWorkflowHarnessProps) {
  const { t } = useTranslation();
  useLanguagePreference(preferredLanguage, instance);

  return (
    <View>
      <LanguageSwitcher storage={storage} />
      <Text>{t("home.description")}</Text>
      <RealtimeStatusNotice
        outcome={classifyRealtimeClose({
          code: 4401,
          reason: "Authentication required.",
        })}
      />
    </View>
  );
}

function renderWorkflow(
  storage: LanguageStorage,
  preferredLanguage?: string,
  instance: i18n = createAppI18n("en"),
) {
  const view = render(
    <LocalizationProvider instance={instance} storage={storage}>
      <LocalizationWorkflowHarness
        instance={instance}
        preferredLanguage={preferredLanguage}
        storage={storage}
      />
    </LocalizationProvider>,
  );

  return { ...view, instance };
}

describe("localization workflow", () => {
  it("persists a manual switch and restores it after a simulated restart", async () => {
    const storage = new MemoryLanguageStorage(null);
    const firstApp = renderWorkflow(storage);

    await waitFor(() => {
      expect(
        screen.getByText("Shared shopping made simple for every family."),
      ).toBeTruthy();
    });
    expect(
      screen.getByText("Your session has expired. Please sign in again."),
    ).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "తెలుగు" }));

    await waitFor(() => {
      expect(storage.value).toBe("te");
      expect(
        screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
      ).toBeTruthy();
      expect(
        screen.getByText("మీ సెషన్ గడువు ముగిసింది. దయచేసి మళ్లీ సైన్ ఇన్ చేయండి."),
      ).toBeTruthy();
    });

    firstApp.unmount();
    const restartedInstance = createAppI18n("en");
    renderWorkflow(storage, undefined, restartedInstance);

    await waitFor(() => {
      expect(restartedInstance.language).toBe("te");
      expect(screen.getByText("భాష")).toBeTruthy();
      expect(
        screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
      ).toBeTruthy();
    });
  });

  it("lets a supported account preference override local persistence", async () => {
    const storage = new MemoryLanguageStorage("te");
    const { instance } = renderWorkflow(storage, "en");

    await waitFor(() => {
      expect(storage.readCount).toBe(1);
      expect(instance.language).toBe("en");
      expect(
        screen.getByText("Shared shopping made simple for every family."),
      ).toBeTruthy();
    });
  });

  it("keeps the restored language for an unsupported account value", async () => {
    const storage = new MemoryLanguageStorage("te");
    const { instance } = renderWorkflow(storage, "fr");

    await waitFor(() => {
      expect(instance.language).toBe("te");
      expect(
        screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
      ).toBeTruthy();
    });
  });
});
