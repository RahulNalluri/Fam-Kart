import {
  GroceryDictionaryEntry,
  buildGroceryAliasIndex,
  findGroceryByAlias,
  groceryDictionaryEntries,
  normalizeGroceryAlias,
} from "../src/features/grocery/dictionary";

describe("grocery dictionary", () => {
  it("provides English and Telugu names for the foundation items", () => {
    expect(groceryDictionaryEntries.length).toBeGreaterThanOrEqual(15);

    for (const entry of groceryDictionaryEntries) {
      expect(entry.key).not.toHaveLength(0);
      expect(entry.names.en).not.toHaveLength(0);
      expect(entry.names.te).not.toHaveLength(0);
      expect(entry.aliases.en.length).toBeGreaterThan(0);
      expect(entry.aliases.te.length).toBeGreaterThan(0);
      expect(entry.aliases.transliterated.length).toBeGreaterThan(0);
    }
  });

  it.each([
    ["  TOMATOES  ", "tomato"],
    ["టమాటాలు", "tomato"],
    ["tamatalu", "tomato"],
    ["పాలు", "milk"],
    ["Palu", "milk"],
    ["godhuma   pindi", "wheat_flour"],
  ])("resolves %s to the canonical %s item", (alias, expectedKey) => {
    expect(findGroceryByAlias(alias)?.key).toBe(expectedKey);
  });

  it("normalizes Unicode width, case, and whitespace", () => {
    expect(normalizeGroceryAlias("  ＭＩＬＫ   ")).toBe("milk");
  });

  it("returns null for blank or unknown items", () => {
    expect(findGroceryByAlias("   ")).toBeNull();
    expect(findGroceryByAlias("dish soap")).toBeNull();
  });

  it("resolves every declared alias to its owning item", () => {
    for (const entry of groceryDictionaryEntries) {
      const aliases = [
        entry.key,
        entry.names.en,
        entry.names.te,
        ...entry.aliases.en,
        ...entry.aliases.te,
        ...entry.aliases.transliterated,
      ];

      for (const alias of aliases) {
        expect(findGroceryByAlias(alias)?.key).toBe(entry.key);
      }
    }
  });

  it("rejects aliases assigned to different canonical items", () => {
    const entries: GroceryDictionaryEntry[] = [
      {
        key: "first",
        names: { en: "First", te: "మొదటి" },
        aliases: { en: ["shared"], te: ["మొదటి"], transliterated: ["modati"] },
      },
      {
        key: "second",
        names: { en: "Second", te: "రెండవ" },
        aliases: { en: ["SHARED"], te: ["రెండవ"], transliterated: ["rendava"] },
      },
    ];

    expect(() => buildGroceryAliasIndex(entries)).toThrow(
      'Grocery alias "shared" belongs to both "first" and "second".',
    );
  });
});
