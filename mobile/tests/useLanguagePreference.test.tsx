import { render, screen, waitFor } from "@testing-library/react-native";
import { i18n } from "i18next";
import { Text } from "react-native";
import { I18nextProvider, useTranslation } from "react-i18next";

import {
  applyLanguagePreference,
  useLanguagePreference,
} from "../src/hooks/useLanguagePreference";
import { createAppI18n } from "../src/locales/i18n";

type LanguagePreferenceHarnessProps = {
  instance: i18n;
  preferredLanguage: string | null | undefined;
};

function LanguagePreferenceHarness({
  instance,
  preferredLanguage,
}: LanguagePreferenceHarnessProps) {
  useLanguagePreference(preferredLanguage, instance);
  const { t } = useTranslation();

  return <Text>{t("home.description")}</Text>;
}

function renderPreference(
  preferredLanguage: string | null | undefined,
  instance: i18n = createAppI18n("en"),
) {
  const view = render(
    <I18nextProvider i18n={instance}>
      <LanguagePreferenceHarness
        instance={instance}
        preferredLanguage={preferredLanguage}
      />
    </I18nextProvider>,
  );

  return { ...view, instance };
}

describe("language preference integration", () => {
  it("applies a supported account preference", async () => {
    const instance = createAppI18n("en");

    await expect(applyLanguagePreference("te", instance)).resolves.toBe(true);

    expect(instance.language).toBe("te");
  });

  it("ignores missing and unsupported account preferences", async () => {
    const instance = createAppI18n("en");

    await expect(applyLanguagePreference(undefined, instance)).resolves.toBe(false);
    await expect(applyLanguagePreference(null, instance)).resolves.toBe(false);
    await expect(applyLanguagePreference("fr", instance)).resolves.toBe(false);

    expect(instance.language).toBe("en");
  });

  it("avoids changing an already active language", async () => {
    const instance = createAppI18n("te");
    const changeLanguage = jest.spyOn(instance, "changeLanguage");

    await expect(applyLanguagePreference("te", instance)).resolves.toBe(false);

    expect(changeLanguage).not.toHaveBeenCalled();
  });

  it("keeps device-selected text while the account profile is loading", () => {
    renderPreference(undefined);

    expect(
      screen.getByText("Shared shopping made simple for every family."),
    ).toBeTruthy();
  });

  it("updates mounted UI when the account preference becomes available", async () => {
    const instance = createAppI18n("en");
    const view = renderPreference(undefined, instance);

    view.rerender(
      <I18nextProvider i18n={instance}>
        <LanguagePreferenceHarness instance={instance} preferredLanguage="te" />
      </I18nextProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
      ).toBeTruthy();
    });
  });
});
