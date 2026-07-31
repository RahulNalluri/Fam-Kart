import { englishTranslations } from "./en";
import { teluguTranslations } from "./te";

export const translationResources = {
  en: {
    translation: englishTranslations,
  },
  te: {
    translation: teluguTranslations,
  },
} as const;
