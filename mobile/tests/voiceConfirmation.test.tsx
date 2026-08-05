import { fireEvent, render, screen } from "@testing-library/react-native";
import { I18nextProvider } from "react-i18next";

import { VoiceConfirmationScreen } from "../src/components/VoiceConfirmationScreen";
import { VoiceConfirmationItem } from "../src/features/voice/confirmation";
import { SupportedLanguage } from "../src/locales/config";
import { createAppI18n } from "../src/locales/i18n";

jest.mock("@expo/vector-icons", () => ({
  Ionicons: () => null,
}));

const milkItem: VoiceConfirmationItem = {
  id: "milk",
  name: "Milk",
  canonicalKey: "milk",
  quantity: "2",
  unit: "packet",
};

const riceItem: VoiceConfirmationItem = {
  id: "rice",
  name: "Rice",
  canonicalKey: "rice",
  quantity: "5",
  unit: "kg",
};

function renderScreen({
  language = "en",
  items = [milkItem, riceItem],
  isSubmitting = false,
  submitError = null,
}: {
  language?: SupportedLanguage;
  items?: readonly VoiceConfirmationItem[];
  isSubmitting?: boolean;
  submitError?: string | null;
} = {}) {
  const onConfirm = jest.fn();
  const onCancel = jest.fn();
  const onRecordAgain = jest.fn();
  const view = render(
    <I18nextProvider i18n={createAppI18n(language)}>
      <VoiceConfirmationScreen
        initialItems={items}
        isSubmitting={isSubmitting}
        onCancel={onCancel}
        onConfirm={onConfirm}
        onRecordAgain={onRecordAgain}
        submitError={submitError}
        transcript="Palu rendu packets and rice five kg"
      />
    </I18nextProvider>,
  );
  return { ...view, onCancel, onConfirm, onRecordAgain };
}

describe("VoiceConfirmationScreen", () => {
  it("shows the transcript and extracted grocery details", () => {
    renderScreen();

    expect(screen.getByRole("header", { name: "Review voice items" })).toBeTruthy();
    expect(screen.getByText("Palu rendu packets and rice five kg")).toBeTruthy();
    expect(screen.getByText("2 items")).toBeTruthy();
    expect(screen.getByLabelText("Item 1 name").props.value).toBe("Milk");
    expect(screen.getByLabelText("Item 2 quantity").props.value).toBe("5");
  });

  it("returns normalized edits only after explicit confirmation", () => {
    const { onConfirm } = renderScreen({ items: [milkItem] });

    fireEvent.changeText(screen.getByLabelText("Item 1 name"), "  Fresh   milk  ");
    fireEvent.changeText(screen.getByLabelText("Item 1 quantity"), "3.5");
    fireEvent.press(
      screen.getByRole("button", { name: "Unit for Fresh milk: Packets" }),
    );
    fireEvent.press(screen.getByRole("menuitem", { name: "Kilograms" }));
    fireEvent.press(screen.getByRole("button", { name: "Add 1 item to list" }));

    expect(onConfirm).toHaveBeenCalledWith([
      {
        ...milkItem,
        canonicalKey: null,
        name: "Fresh milk",
        quantity: "3.5",
        unit: "kg",
      },
    ]);
  });

  it("removes incorrect items and blocks an empty confirmation", () => {
    const { onConfirm } = renderScreen({ items: [milkItem] });

    fireEvent.press(screen.getByRole("button", { name: "Remove Milk" }));

    expect(
      screen.getByText("No items remain. Record again or cancel this voice command."),
    ).toBeTruthy();
    const confirmButton = screen.getByRole("button", { name: "Add 0 items to list" });
    expect(confirmButton.props.accessibilityState.disabled).toBe(true);
    fireEvent.press(confirmButton);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows validation errors and blocks invalid quantities", () => {
    const { onConfirm } = renderScreen({ items: [milkItem] });

    fireEvent.changeText(screen.getByLabelText("Item 1 quantity"), "0");

    expect(
      screen.getByText("Enter a positive quantity with up to three decimal places."),
    ).toBeTruthy();
    const confirmButton = screen.getByRole("button", { name: "Add 1 item to list" });
    expect(confirmButton.props.accessibilityState.disabled).toBe(true);
    fireEvent.press(confirmButton);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("requires quantity for a selected unit and allows clearing the unit", () => {
    renderScreen({ items: [{ ...milkItem, quantity: "" }] });

    expect(screen.getByText("Enter a quantity when a unit is selected.")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Unit for Milk: Packets" }));
    fireEvent.press(screen.getByRole("menuitem", { name: "No unit" }));

    expect(screen.queryByText("Enter a quantity when a unit is selected.")).toBeNull();
  });

  it("provides cancel and record-again actions", () => {
    const { onCancel, onRecordAgain } = renderScreen();

    fireEvent.press(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.press(screen.getByRole("button", { name: "Record again" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onRecordAgain).toHaveBeenCalledTimes(1);
  });

  it("disables actions and presents errors while submission is controlled upstream", () => {
    const { onConfirm } = renderScreen({
      items: [milkItem],
      isSubmitting: true,
      submitError: "Items could not be added.",
    });

    expect(
      screen.getByRole("alert", { name: "Items could not be added." }),
    ).toBeTruthy();
    const submitButton = screen.getByRole("button", { name: "Adding items..." });
    expect(submitButton.props.accessibilityState).toEqual({
      busy: true,
      disabled: true,
    });
    fireEvent.press(submitButton);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders the confirmation workflow in Telugu", () => {
    renderScreen({ language: "te", items: [milkItem] });

    expect(screen.getByText("వాయిస్ సరుకులను తనిఖీ చేయండి")).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "1 సరుకును జాబితాకు జోడించండి",
      }),
    ).toBeTruthy();
  });
});
