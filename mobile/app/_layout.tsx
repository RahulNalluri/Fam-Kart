import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { I18nextProvider } from "react-i18next";

import { appI18n } from "../src/locales/i18n";
import { appQueryClient } from "../src/services/queryClient";

export default function RootLayout() {
  return (
    <I18nextProvider i18n={appI18n}>
      <QueryClientProvider client={appQueryClient}>
        <Stack
          screenOptions={{
            headerShown: false,
          }}
        />
      </QueryClientProvider>
    </I18nextProvider>
  );
}
