import { render, screen, waitFor } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import HomeScreen from "../app/index";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";
import { getHealth } from "../src/services/api";

jest.mock("../src/services/api", () => ({
  getHealth: jest.fn(),
}));

const mockedGetHealth = jest.mocked(getHealth);

function renderHome(language: SupportedLanguage = "en") {
  return render(
    <I18nextProvider i18n={createAppI18n(language)}>
      <HomeScreen />
    </I18nextProvider>,
  );
}

describe("HomeScreen", () => {
  beforeEach(() => {
    mockedGetHealth.mockReset();
  });

  it("renders the application title", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    renderHome();

    expect(screen.getByText("FamilyKart AI")).toBeTruthy();
  });

  it("renders the description", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    renderHome();

    expect(
      screen.getByText("Shared shopping made simple for every family."),
    ).toBeTruthy();
  });

  it("renders the loading state", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    renderHome();

    expect(screen.getByText("Backend status: Checking...")).toBeTruthy();
    expect(screen.getByLabelText("Checking backend status")).toBeTruthy();
  });

  it("renders the connected state after a successful API response", async () => {
    mockedGetHealth.mockResolvedValue({
      status: "healthy",
      service: "familykart-api",
      version: "0.1.0",
    });

    renderHome();

    await waitFor(() => {
      expect(screen.getByText("Backend status: Connected")).toBeTruthy();
    });
  });

  it("renders the error state after a failed API response", async () => {
    mockedGetHealth.mockRejectedValue(new Error("Network error"));

    renderHome();

    await waitFor(() => {
      expect(screen.getByText("Backend status: Unavailable")).toBeTruthy();
    });
  });

  it("renders Telugu text when Telugu is active", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    renderHome("te");

    expect(
      screen.getByText("ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం."),
    ).toBeTruthy();
    expect(screen.getByText("బ్యాక్‌ఎండ్ స్థితి: తనిఖీ చేస్తోంది...")).toBeTruthy();
    expect(screen.getByLabelText("బ్యాక్‌ఎండ్ స్థితిని తనిఖీ చేస్తోంది")).toBeTruthy();
  });
});
