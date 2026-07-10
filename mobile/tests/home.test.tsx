import { render, screen, waitFor } from "@testing-library/react-native";

import HomeScreen from "../app/index";
import { getHealth } from "../src/services/api";

jest.mock("../src/services/api", () => ({
  getHealth: jest.fn(),
}));

const mockedGetHealth = jest.mocked(getHealth);

describe("HomeScreen", () => {
  beforeEach(() => {
    mockedGetHealth.mockReset();
  });

  it("renders the application title", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    render(<HomeScreen />);

    expect(screen.getByText("FamilyKart AI")).toBeTruthy();
  });

  it("renders the description", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    render(<HomeScreen />);

    expect(
      screen.getByText("Shared shopping made simple for every family."),
    ).toBeTruthy();
  });

  it("renders the loading state", () => {
    mockedGetHealth.mockImplementation(() => new Promise(() => undefined));

    render(<HomeScreen />);

    expect(screen.getByText("Backend status: Checking...")).toBeTruthy();
    expect(screen.getByLabelText("Checking backend status")).toBeTruthy();
  });

  it("renders the connected state after a successful API response", async () => {
    mockedGetHealth.mockResolvedValue({
      status: "healthy",
      service: "familykart-api",
      version: "0.1.0",
    });

    render(<HomeScreen />);

    await waitFor(() => {
      expect(screen.getByText("Backend status: Connected")).toBeTruthy();
    });
  });

  it("renders the error state after a failed API response", async () => {
    mockedGetHealth.mockRejectedValue(new Error("Network error"));

    render(<HomeScreen />);

    await waitFor(() => {
      expect(screen.getByText("Backend status: Unavailable")).toBeTruthy();
    });
  });
});
