import { TranslationResources } from "./types";

export const englishTranslations = {
  common: {
    appName: "FamilyKart AI",
  },
  languageSwitcher: {
    label: "Language",
    english: "English",
    telugu: "తెలుగు",
  },
  home: {
    description: "Shared shopping made simple for every family.",
    backendStatus: {
      label: "Backend status",
      checking: "Checking...",
      connected: "Connected",
      unavailable: "Unavailable",
      checkingAccessibilityLabel: "Checking backend status",
    },
  },
  realtime: {
    normal: "Real-time updates stopped normally.",
    authenticationRequired: "Your session has expired. Please sign in again.",
    householdUnavailable: "This household is no longer available to your account.",
    serviceUnavailable: "Real-time updates are temporarily unavailable. Reconnecting.",
    connectionInterrupted: "The real-time connection was interrupted. Reconnecting.",
  },
  voice: {
    permission: {
      title: "Microphone permission",
      rationale:
        "FamilyKart AI needs microphone access to add grocery items using your voice.",
      request: "Allow microphone",
      denied: "Allow microphone access to use voice input.",
      blocked:
        "Microphone access is blocked. Allow it from your phone settings to use voice input.",
      openSettings: "Open settings",
    },
  },
} satisfies TranslationResources;
