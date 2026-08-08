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
  offline: {
    conflicts: {
      title: string;
      count_one: string;
      count_other: string;
      loading: string;
      empty: string;
      itemFallback: string;
      summary: string;
      operations: {
        add: string;
        edit: string;
        complete: string;
        reopen: string;
        delete: string;
      };
      quantity: string;
      unit: string;
      reasons: {
        serverConflict: string;
        invalidMutation: string;
        reviewRequired: string;
      };
      keepFamilyVersion: string;
      reviewChange: string;
      resolving: string;
      loadFailed: string;
      resolveFailed: string;
    };
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
    confirmation: {
      title: string;
      subtitle: string;
      heardLabel: string;
      itemsLabel: string;
      itemCount_one: string;
      itemCount_other: string;
      itemName: string;
      itemNameAccessibility: string;
      quantity: string;
      quantityAccessibility: string;
      quantityPlaceholder: string;
      unit: string;
      unitAccessibility: string;
      noUnit: string;
      selectUnit: string;
      closeUnitMenu: string;
      removeItem: string;
      nameRequired: string;
      nameTooLong: string;
      quantityInvalid: string;
      quantityRequiredForUnit: string;
      empty: string;
      cancel: string;
      recordAgain: string;
      confirm_one: string;
      confirm_other: string;
      submitting: string;
      errors: {
        networkUnavailable: string;
        sessionExpired: string;
        householdUnavailable: string;
        saveFailed: string;
      };
      units: {
        kg: string;
        g: string;
        l: string;
        ml: string;
        packet: string;
        piece: string;
        dozen: string;
        bottle: string;
        box: string;
        bag: string;
        bunch: string;
        can: string;
        jar: string;
      };
    };
  };
};
