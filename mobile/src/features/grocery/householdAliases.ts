import {
  GroceryDictionaryEntry,
  GroceryItemKey,
  findGroceryByAlias,
  groceryAliasIndex,
  groceryDictionaryEntries,
  normalizeGroceryAlias,
} from "./dictionary";

export type HouseholdGroceryAlias = {
  alias: string;
  canonicalKey: string;
};

export type HouseholdAliasIndex = ReadonlyMap<string, GroceryDictionaryEntry>;

const groceryEntriesByKey = new Map<GroceryItemKey, GroceryDictionaryEntry>(
  groceryDictionaryEntries.map((entry) => [entry.key, entry]),
);

function getCanonicalEntry(canonicalKey: string): GroceryDictionaryEntry {
  const entry = groceryEntriesByKey.get(canonicalKey as GroceryItemKey);
  if (!entry) {
    throw new Error(`Unknown canonical grocery key "${canonicalKey}".`);
  }
  return entry;
}

export function buildHouseholdAliasIndex(
  aliases: readonly HouseholdGroceryAlias[],
): HouseholdAliasIndex {
  const index = new Map<string, GroceryDictionaryEntry>();

  for (const householdAlias of aliases) {
    const normalizedAlias = normalizeGroceryAlias(householdAlias.alias);
    if (!normalizedAlias) {
      throw new Error("Household grocery aliases cannot be blank.");
    }

    const canonicalEntry = getCanonicalEntry(householdAlias.canonicalKey);
    const dictionaryEntry = groceryAliasIndex.get(normalizedAlias);
    if (dictionaryEntry && dictionaryEntry.key !== canonicalEntry.key) {
      throw new Error(
        `Household alias "${normalizedAlias}" cannot replace the standard "${dictionaryEntry.key}" item.`,
      );
    }

    const existingEntry = index.get(normalizedAlias);
    if (existingEntry && existingEntry.key !== canonicalEntry.key) {
      throw new Error(
        `Household alias "${normalizedAlias}" belongs to both "${existingEntry.key}" and "${canonicalEntry.key}".`,
      );
    }

    index.set(normalizedAlias, canonicalEntry);
  }

  return index;
}

export function findGroceryWithHouseholdAliases(
  value: string,
  householdAliases: HouseholdAliasIndex,
): GroceryDictionaryEntry | null {
  const normalizedAlias = normalizeGroceryAlias(value);
  if (!normalizedAlias) {
    return null;
  }

  return householdAliases.get(normalizedAlias) ?? findGroceryByAlias(normalizedAlias);
}
