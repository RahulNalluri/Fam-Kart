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
  voice: {
    permission: {
      title: string;
      rationale: string;
      request: string;
      denied: string;
      blocked: string;
      openSettings: string;
    };
    recorder: {
      title: string;
      idle: string;
      requestingPermission: string;
      preparing: string;
      recording: string;
      stopping: string;
      ready: string;
      failed: string;
      start: string;
      stop: string;
      cancel: string;
      recordAgain: string;
      durationAccessibility: string;
    };
  };
};
