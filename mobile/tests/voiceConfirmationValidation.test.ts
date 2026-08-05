import {
  isVoiceConfirmationValid,
  normalizeVoiceConfirmationItem,
  validateVoiceConfirmationItem,
  VoiceConfirmationItem,
} from "../src/features/voice/confirmation";

function item(overrides: Partial<VoiceConfirmationItem> = {}): VoiceConfirmationItem {
  return {
    id: "milk",
    name: "Milk",
    canonicalKey: "milk",
    quantity: "2",
    unit: "packet",
    ...overrides,
  };
}

describe("voice confirmation validation", () => {
  it("normalizes names and quantities without changing stable metadata", () => {
    expect(
      normalizeVoiceConfirmationItem(
        item({ name: "  Fresh   milk  ", quantity: " 2.500 " }),
      ),
    ).toEqual(
      item({
        name: "Fresh milk",
        quantity: "2.500",
      }),
    );
  });

  it("accepts positive quantities with up to seven integer and three decimal digits", () => {
    expect(validateVoiceConfirmationItem(item({ quantity: "1234567.123" }))).toEqual({
      name: null,
      quantity: null,
    });
  });

  it.each(["0", "-1", "1.2345", "12345678", "1e2", "words"])(
    "rejects invalid quantity %s",
    (quantity) => {
      expect(validateVoiceConfirmationItem(item({ quantity })).quantity).toBe(
        "invalid",
      );
    },
  );

  it("requires a quantity when a unit is selected", () => {
    expect(validateVoiceConfirmationItem(item({ quantity: "" })).quantity).toBe(
      "required_for_unit",
    );
    expect(
      validateVoiceConfirmationItem(item({ quantity: "", unit: null })).quantity,
    ).toBeNull();
  });

  it("rejects blank and oversized item names", () => {
    expect(validateVoiceConfirmationItem(item({ name: "   " })).name).toBe("required");
    expect(validateVoiceConfirmationItem(item({ name: "a".repeat(161) })).name).toBe(
      "too_long",
    );
  });

  it("requires at least one valid item before confirmation", () => {
    expect(isVoiceConfirmationValid([])).toBe(false);
    expect(isVoiceConfirmationValid([item()])).toBe(true);
    expect(isVoiceConfirmationValid([item({ name: "" })])).toBe(false);
  });
});
