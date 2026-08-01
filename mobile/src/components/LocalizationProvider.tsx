import { i18n } from "i18next";
import { ReactNode, useEffect, useState } from "react";
import { I18nextProvider } from "react-i18next";

import { appI18n, changeAppLanguage } from "../locales/i18n";
import {
  LanguageStorage,
  loadSelectedLanguage,
  secureLanguageStorage,
} from "../locales/languageStorage";

export type LocalizationProviderProps = {
  children: ReactNode;
  instance?: i18n;
  storage?: LanguageStorage;
};

export function LocalizationProvider({
  children,
  instance = appI18n,
  storage = secureLanguageStorage,
}: LocalizationProviderProps) {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function restoreLanguage() {
      try {
        const savedLanguage = await loadSelectedLanguage(storage);
        if (isMounted) {
          await changeAppLanguage(savedLanguage, instance);
        }
      } finally {
        if (isMounted) {
          setIsReady(true);
        }
      }
    }

    void restoreLanguage().catch(() => undefined);

    return () => {
      isMounted = false;
    };
  }, [instance, storage]);

  return <I18nextProvider i18n={instance}>{isReady ? children : null}</I18nextProvider>;
}
