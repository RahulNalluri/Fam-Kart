import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";

import { appQueryClient } from "../src/services/queryClient";

export default function RootLayout() {
  return (
    <QueryClientProvider client={appQueryClient}>
      <Stack
        screenOptions={{
          headerShown: false,
        }}
      />
    </QueryClientProvider>
  );
}
