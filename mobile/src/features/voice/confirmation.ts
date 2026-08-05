export const GROCERY_UNITS = [
  "kg",
  "g",
  "l",
  "ml",
  "packet",
  "piece",
  "dozen",
  "bottle",
  "box",
  "bag",
  "bunch",
  "can",
  "jar",
] as const;

export type GroceryUnit = (typeof GROCERY_UNITS)[number];

export type VoiceConfirmationSubmitErrorCode =
  "network_unavailable" | "session_expired" | "household_unavailable" | "save_failed";

export type VoiceConfirmationItem = Readonly<{
  id: string;
  name: string;
  canonicalKey: string | null;
  quantity: string;
  unit: GroceryUnit | null;
}>;

export type VoiceConfirmationItemErrors = Readonly<{
  name: "required" | "too_long" | null;
  quantity: "invalid" | "required_for_unit" | null;
}>;

const quantityPattern = /^\d{1,7}(?:\.\d{1,3})?$/;

export function normalizeVoiceConfirmationItem(
  item: VoiceConfirmationItem,
): VoiceConfirmationItem {
  return {
    ...item,
    name: item.name.normalize("NFKC").trim().replace(/\s+/g, " "),
    quantity: item.quantity.trim(),
  };
}

export function validateVoiceConfirmationItem(
  item: VoiceConfirmationItem,
): VoiceConfirmationItemErrors {
  const normalized = normalizeVoiceConfirmationItem(item);
  const nameError = !normalized.name
    ? "required"
    : normalized.name.length > 160
      ? "too_long"
      : null;

  let quantityError: VoiceConfirmationItemErrors["quantity"] = null;
  if (!normalized.quantity && normalized.unit) {
    quantityError = "required_for_unit";
  } else if (
    normalized.quantity &&
    (!quantityPattern.test(normalized.quantity) || Number(normalized.quantity) <= 0)
  ) {
    quantityError = "invalid";
  }

  return {
    name: nameError,
    quantity: quantityError,
  };
}

export function isVoiceConfirmationValid(
  items: readonly VoiceConfirmationItem[],
): boolean {
  return (
    items.length > 0 &&
    items.every((item) => {
      const errors = validateVoiceConfirmationItem(item);
      return errors.name === null && errors.quantity === null;
    })
  );
}
