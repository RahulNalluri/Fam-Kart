import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";

import { LocalizationProvider } from "../src/components/LocalizationProvider";
import { appQueryClient } from "../src/services/queryClient";

export default function RootLayout() {
  return (
    <LocalizationProvider>
      <QueryClientProvider client={appQueryClient}>
        <Stack
          screenOptions={{
            headerShown: false,
          }}
        />
      </QueryClientProvider>
    </LocalizationProvider>
  );
}
