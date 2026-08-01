import { render, screen, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";
import { useTranslation } from "react-i18next";

import { LocalizationProvider } from "../src/components/LocalizationProvider";
import { createAppI18n } from "../src/locales/i18n";
import { LanguageStorage } from "../src/locales/languageStorage";

function TranslationProbe() {
  const { t } = useTranslation();
  return <Text>{t("home.description")}</Text>;
}

function createStorage(value: string | null): LanguageStorage {
  return {
    getItemAsync: jest.fn().mockResolvedValue(value),
    setItemAsync: jest.fn().mockResolvedValue(undefined),
  };
}

describe("LocalizationProvider", () => {
  it("restores a saved language before rendering the application", async () => {
    render(
      <LocalizationProvider
        instance={createAppI18n("en")}
        storage={createStorage("te")}
      >
        <TranslationProbe />
      </LocalizationProvider>,
    );

    expect(
      screen.queryByText("Shared shopping made simple for every family."),
    ).toBeNull();
    await waitFor(() => {
      expect(
        screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
      ).toBeTruthy();
    });
  });

  it("keeps the device language when no saved selection exists", async () => {
    render(
      <LocalizationProvider
        instance={createAppI18n("en")}
        storage={createStorage(null)}
      >
        <TranslationProbe />
      </LocalizationProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Shared shopping made simple for every family."),
      ).toBeTruthy();
    });
  });

  it("continues with the device language when storage cannot be read", async () => {
    const storage = createStorage(null);
    storage.getItemAsync = jest.fn().mockRejectedValue(new Error("Unavailable"));

    render(
      <LocalizationProvider instance={createAppI18n("en")} storage={storage}>
        <TranslationProbe />
      </LocalizationProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Shared shopping made simple for every family."),
      ).toBeTruthy();
    });
  });
});
