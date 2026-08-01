import { SupportedLanguage } from "../../locales/config";

export type GroceryAliasGroup = "en" | "te" | "transliterated";

export type GroceryDictionaryEntry = {
  key: string;
  names: Record<SupportedLanguage, string>;
  aliases: Record<GroceryAliasGroup, readonly string[]>;
};

export const groceryDictionaryEntries = [
  {
    key: "rice",
    names: { en: "Rice", te: "బియ్యం" },
    aliases: { en: ["rice"], te: ["బియ్యం"], transliterated: ["biyyam"] },
  },
  {
    key: "milk",
    names: { en: "Milk", te: "పాలు" },
    aliases: { en: ["milk"], te: ["పాలు"], transliterated: ["palu"] },
  },
  {
    key: "tomato",
    names: { en: "Tomato", te: "టమాటా" },
    aliases: {
      en: ["tomato", "tomatoes"],
      te: ["టమాటా", "టమాటాలు"],
      transliterated: ["tamata", "tamatalu"],
    },
  },
  {
    key: "onion",
    names: { en: "Onion", te: "ఉల్లిపాయ" },
    aliases: {
      en: ["onion", "onions"],
      te: ["ఉల్లిపాయ", "ఉల్లిపాయలు"],
      transliterated: ["ullipaya", "ullipayalu"],
    },
  },
  {
    key: "potato",
    names: { en: "Potato", te: "బంగాళాదుంప" },
    aliases: {
      en: ["potato", "potatoes"],
      te: ["బంగాళాదుంప", "బంగాళాదుంపలు"],
      transliterated: ["bangaladumpa", "bangaladumpalu", "aloo"],
    },
  },
  {
    key: "egg",
    names: { en: "Egg", te: "గుడ్డు" },
    aliases: {
      en: ["egg", "eggs"],
      te: ["గుడ్డు", "గుడ్లు"],
      transliterated: ["guddu", "gudlu"],
    },
  },
  {
    key: "curd",
    names: { en: "Curd", te: "పెరుగు" },
    aliases: {
      en: ["curd", "yogurt", "yoghurt"],
      te: ["పెరుగు"],
      transliterated: ["perugu"],
    },
  },
  {
    key: "dal",
    names: { en: "Dal", te: "పప్పు" },
    aliases: {
      en: ["dal", "lentil", "lentils"],
      te: ["పప్పు"],
      transliterated: ["pappu"],
    },
  },
  {
    key: "salt",
    names: { en: "Salt", te: "ఉప్పు" },
    aliases: { en: ["salt"], te: ["ఉప్పు"], transliterated: ["uppu"] },
  },
  {
    key: "sugar",
    names: { en: "Sugar", te: "చక్కెర" },
    aliases: {
      en: ["sugar"],
      te: ["చక్కెర"],
      transliterated: ["chakkera"],
    },
  },
  {
    key: "cooking_oil",
    names: { en: "Cooking oil", te: "వంట నూనె" },
    aliases: {
      en: ["oil", "cooking oil"],
      te: ["నూనె", "వంట నూనె"],
      transliterated: ["nune", "noone", "vanta nune"],
    },
  },
  {
    key: "wheat_flour",
    names: { en: "Wheat flour", te: "గోధుమ పిండి" },
    aliases: {
      en: ["wheat flour", "atta"],
      te: ["గోధుమ పిండి"],
      transliterated: ["godhuma pindi"],
    },
  },
  {
    key: "chilli",
    names: { en: "Chilli", te: "మిరపకాయ" },
    aliases: {
      en: ["chilli", "chillies", "chili", "chilies"],
      te: ["మిరపకాయ", "మిరపకాయలు"],
      transliterated: ["mirapakaya", "mirapakayalu"],
    },
  },
  {
    key: "garlic",
    names: { en: "Garlic", te: "వెల్లుల్లి" },
    aliases: {
      en: ["garlic"],
      te: ["వెల్లుల్లి"],
      transliterated: ["vellulli"],
    },
  },
  {
    key: "ginger",
    names: { en: "Ginger", te: "అల్లం" },
    aliases: { en: ["ginger"], te: ["అల్లం"], transliterated: ["allam"] },
  },
] as const satisfies readonly GroceryDictionaryEntry[];

export type GroceryItemKey = (typeof groceryDictionaryEntries)[number]["key"];

export function normalizeGroceryAlias(value: string): string {
  return value.normalize("NFKC").trim().toLocaleLowerCase("en").replace(/\s+/gu, " ");
}

function entryAliases(entry: GroceryDictionaryEntry): readonly string[] {
  return [
    entry.key,
    entry.names.en,
    entry.names.te,
    ...entry.aliases.en,
    ...entry.aliases.te,
    ...entry.aliases.transliterated,
  ];
}

export function buildGroceryAliasIndex(
  entries: readonly GroceryDictionaryEntry[],
): ReadonlyMap<string, GroceryDictionaryEntry> {
  const index = new Map<string, GroceryDictionaryEntry>();

  for (const entry of entries) {
    for (const alias of entryAliases(entry)) {
      const normalizedAlias = normalizeGroceryAlias(alias);
      if (!normalizedAlias) {
        throw new Error(`Grocery item "${entry.key}" contains a blank alias.`);
      }

      const existingEntry = index.get(normalizedAlias);
      if (existingEntry && existingEntry.key !== entry.key) {
        throw new Error(
          `Grocery alias "${normalizedAlias}" belongs to both "${existingEntry.key}" and "${entry.key}".`,
        );
      }

      index.set(normalizedAlias, entry);
    }
  }

  return index;
}

export const groceryAliasIndex = buildGroceryAliasIndex(groceryDictionaryEntries);

export function findGroceryByAlias(value: string): GroceryDictionaryEntry | null {
  const normalizedAlias = normalizeGroceryAlias(value);
  return normalizedAlias ? (groceryAliasIndex.get(normalizedAlias) ?? null) : null;
}
