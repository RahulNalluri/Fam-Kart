import {
  buildHouseholdAliasIndex,
  findGroceryWithHouseholdAliases,
} from "../src/features/grocery/householdAliases";

describe("household grocery aliases", () => {
  it.each([
    ["morning milk", "milk"],
    ["ఉల్లిగడ్డ", "onion"],
    ["ulli gadda", "onion"],
  ])("resolves the household alias %s", (alias, expectedKey) => {
    const index = buildHouseholdAliasIndex([
      { alias: "morning milk", canonicalKey: "milk" },
      { alias: "ఉల్లిగడ్డ", canonicalKey: "onion" },
      { alias: "ulli gadda", canonicalKey: "onion" },
    ]);

    expect(findGroceryWithHouseholdAliases(alias, index)?.key).toBe(expectedKey);
  });

  it("normalizes household aliases before lookup", () => {
    const index = buildHouseholdAliasIndex([
      { alias: "  Curry   Onions ", canonicalKey: "onion" },
    ]);

    expect(findGroceryWithHouseholdAliases("CURRY ONIONS", index)?.key).toBe("onion");
  });

  it("falls back to the standard grocery dictionary", () => {
    const index = buildHouseholdAliasIndex([]);

    expect(findGroceryWithHouseholdAliases("టమాటాలు", index)?.key).toBe("tomato");
    expect(findGroceryWithHouseholdAliases("Palu", index)?.key).toBe("milk");
  });

  it("keeps alias indexes isolated between households", () => {
    const firstHousehold = buildHouseholdAliasIndex([
      { alias: "weekly item", canonicalKey: "rice" },
    ]);
    const secondHousehold = buildHouseholdAliasIndex([
      { alias: "weekly item", canonicalKey: "wheat_flour" },
    ]);

    expect(findGroceryWithHouseholdAliases("weekly item", firstHousehold)?.key).toBe(
      "rice",
    );
    expect(findGroceryWithHouseholdAliases("weekly item", secondHousehold)?.key).toBe(
      "wheat_flour",
    );
  });

  it("returns null for blank and unknown input", () => {
    const index = buildHouseholdAliasIndex([]);

    expect(findGroceryWithHouseholdAliases("   ", index)).toBeNull();
    expect(findGroceryWithHouseholdAliases("family special", index)).toBeNull();
  });

  it("rejects an unknown canonical grocery key", () => {
    expect(() =>
      buildHouseholdAliasIndex([
        { alias: "cleaning liquid", canonicalKey: "dish_soap" },
      ]),
    ).toThrow('Unknown canonical grocery key "dish_soap".');
  });

  it("rejects blank aliases", () => {
    expect(() =>
      buildHouseholdAliasIndex([{ alias: "  ", canonicalKey: "milk" }]),
    ).toThrow("Household grocery aliases cannot be blank.");
  });

  it("prevents a household alias from remapping a standard term", () => {
    expect(() =>
      buildHouseholdAliasIndex([{ alias: "milk", canonicalKey: "rice" }]),
    ).toThrow('Household alias "milk" cannot replace the standard "milk" item.');
  });

  it("rejects one household alias assigned to different items", () => {
    expect(() =>
      buildHouseholdAliasIndex([
        { alias: "regular item", canonicalKey: "rice" },
        { alias: "REGULAR ITEM", canonicalKey: "dal" },
      ]),
    ).toThrow('Household alias "regular item" belongs to both "rice" and "dal".');
  });

  it("allows equivalent duplicate aliases for the same item", () => {
    const index = buildHouseholdAliasIndex([
      { alias: "Breakfast Milk", canonicalKey: "milk" },
      { alias: " breakfast   milk ", canonicalKey: "milk" },
    ]);

    expect(index.size).toBe(1);
    expect(findGroceryWithHouseholdAliases("breakfast milk", index)?.key).toBe("milk");
  });
});
