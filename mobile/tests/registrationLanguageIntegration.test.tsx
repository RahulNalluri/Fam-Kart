import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { AxiosResponse } from "axios";
import { Pressable, Text, View } from "react-native";
import { I18nextProvider } from "react-i18next";

import { LanguageSwitcher } from "../src/components/LanguageSwitcher";
import { registerAccount } from "../src/features/auth/registration";
import {
  resolveRegistrationLanguage,
  useRegistrationLanguage,
} from "../src/hooks/useRegistrationLanguage";
import { createAppI18n } from "../src/locales/i18n";
import { LanguageStorage } from "../src/locales/languageStorage";
import api from "../src/services/api";

jest.mock("../src/services/api", () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
  },
}));

const userId = "11111111-1111-4111-8111-111111111111";
const registeredUserResponse = {
  id: userId,
  email: "rahul@example.com",
  display_name: "Rahul",
  preferred_language: "te",
  is_active: true,
  created_at: "2026-08-02T12:00:00Z",
};

const postMock = api.post as jest.MockedFunction<typeof api.post>;

function responseWith(data: unknown): AxiosResponse<unknown> {
  return {
    data,
    status: 201,
    statusText: "Created",
    headers: {},
    config: { headers: {} } as AxiosResponse["config"],
  };
}

function RegistrationLanguageHarness({ storage }: { storage: LanguageStorage }) {
  const preferredLanguage = useRegistrationLanguage();

  return (
    <View>
      <LanguageSwitcher storage={storage} />
      <Text testID="registration-language">{preferredLanguage}</Text>
      <Pressable
        accessibilityLabel="Create account"
        accessibilityRole="button"
        onPress={() => {
          void registerAccount({
            email: "  RAHUL@EXAMPLE.COM ",
            displayName: "  Rahul  ",
            password: "familykart123",
            preferredLanguage,
          });
        }}
      >
        <Text>Create account</Text>
      </Pressable>
    </View>
  );
}

describe("registration language integration", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("submits the language selected through the real language switcher", async () => {
    const instance = createAppI18n("en");
    const storage: jest.Mocked<LanguageStorage> = {
      getItemAsync: jest.fn().mockResolvedValue(null),
      setItemAsync: jest.fn().mockResolvedValue(undefined),
    };
    postMock.mockResolvedValue(responseWith(registeredUserResponse));
    render(
      <I18nextProvider i18n={instance}>
        <RegistrationLanguageHarness storage={storage} />
      </I18nextProvider>,
    );

    fireEvent.press(
      screen.getByRole("button", {
        name: instance.t("languageSwitcher.telugu"),
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("registration-language").props.children).toBe("te");
    });
    fireEvent.press(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/api/v1/auth/register", {
        email: "rahul@example.com",
        display_name: "Rahul",
        password: "familykart123",
        preferred_language: "te",
      });
    });
    expect(storage.setItemAsync).toHaveBeenCalledWith(
      "familykart.selected-language",
      "te",
    );
  });

  it("converts the registered profile to the mobile contract", async () => {
    postMock.mockResolvedValue(responseWith(registeredUserResponse));

    await expect(
      registerAccount({
        email: "rahul@example.com",
        displayName: "Rahul",
        password: "familykart123",
        preferredLanguage: "te",
      }),
    ).resolves.toEqual({
      id: userId,
      email: "rahul@example.com",
      displayName: "Rahul",
      preferredLanguage: "te",
      isActive: true,
      createdAt: "2026-08-02T12:00:00Z",
    });
  });

  it("falls back safely when i18next contains an unsupported language", () => {
    expect(
      resolveRegistrationLanguage({
        language: "fr",
        resolvedLanguage: "fr",
      }),
    ).toBe("en");
    expect(
      resolveRegistrationLanguage({
        language: "te-IN",
        resolvedLanguage: "te",
      }),
    ).toBe("te");
  });

  it("rejects invalid registration input before calling the backend", async () => {
    await expect(
      registerAccount({
        email: "not-an-email",
        displayName: "Rahul",
        password: "familykart123",
        preferredLanguage: "te",
      }),
    ).rejects.toBeDefined();

    expect(postMock).not.toHaveBeenCalled();
  });

  it("rejects a malformed registered-user response", async () => {
    postMock.mockResolvedValue(
      responseWith({ ...registeredUserResponse, preferred_language: "fr" }),
    );

    await expect(
      registerAccount({
        email: "rahul@example.com",
        displayName: "Rahul",
        password: "familykart123",
        preferredLanguage: "te",
      }),
    ).rejects.toBeDefined();
  });

  it("preserves backend registration errors for future UI handling", async () => {
    const duplicateError = new Error("An account with this email already exists.");
    postMock.mockRejectedValue(duplicateError);

    await expect(
      registerAccount({
        email: "rahul@example.com",
        displayName: "Rahul",
        password: "familykart123",
        preferredLanguage: "en",
      }),
    ).rejects.toBe(duplicateError);
  });
});
