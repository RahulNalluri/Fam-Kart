import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import {
  SUPPORTED_LANGUAGES,
  SupportedLanguage,
  isSupportedLanguage,
} from "../locales/config";
import { changeAppLanguage } from "../locales/i18n";

const languageLabelKeys = {
  en: "languageSwitcher.english",
  te: "languageSwitcher.telugu",
} as const satisfies Record<SupportedLanguage, string>;

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const [isChanging, setIsChanging] = useState(false);
  const activeLanguage = isSupportedLanguage(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : isSupportedLanguage(i18n.language)
      ? i18n.language
      : null;

  async function selectLanguage(language: SupportedLanguage) {
    setIsChanging(true);
    try {
      await changeAppLanguage(language, i18n);
    } finally {
      setIsChanging(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{t("languageSwitcher.label")}</Text>
      <View style={styles.options}>
        {SUPPORTED_LANGUAGES.map((language) => {
          const isSelected = activeLanguage === language;
          return (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: isChanging, selected: isSelected }}
              disabled={isChanging}
              key={language}
              onPress={() => void selectLanguage(language).catch(() => undefined)}
              style={({ pressed }) => [
                styles.option,
                isSelected ? styles.selectedOption : styles.unselectedOption,
                pressed && !isChanging ? styles.pressedOption : null,
              ]}
            >
              <Text
                style={[
                  styles.optionText,
                  isSelected ? styles.selectedOptionText : styles.unselectedOptionText,
                ]}
              >
                {t(languageLabelKeys[language])}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "flex-start",
    gap: 8,
  },
  label: {
    color: "#3E5145",
    fontSize: 14,
    fontWeight: "600",
  },
  option: {
    alignItems: "center",
    height: 44,
    justifyContent: "center",
    minWidth: 104,
    paddingHorizontal: 16,
  },
  options: {
    borderColor: "#92A79A",
    borderRadius: 6,
    borderWidth: 1,
    flexDirection: "row",
    overflow: "hidden",
  },
  optionText: {
    fontSize: 15,
    fontWeight: "700",
  },
  pressedOption: {
    opacity: 0.72,
  },
  selectedOption: {
    backgroundColor: "#1E5B3A",
  },
  selectedOptionText: {
    color: "#FFFFFF",
  },
  unselectedOption: {
    backgroundColor: "#FFFFFF",
  },
  unselectedOptionText: {
    color: "#1E3528",
  },
});
