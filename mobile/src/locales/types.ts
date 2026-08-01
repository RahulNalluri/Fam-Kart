export type TranslationResources = {
  common: {
    appName: string;
  };
  languageSwitcher: {
    label: string;
    english: string;
    telugu: string;
  };
  home: {
    description: string;
    backendStatus: {
      label: string;
      checking: string;
      connected: string;
      unavailable: string;
      checkingAccessibilityLabel: string;
    };
  };
  realtime: {
    normal: string;
    authenticationRequired: string;
    householdUnavailable: string;
    serviceUnavailable: string;
    connectionInterrupted: string;
  };
};
