import { TranslationResources } from "./types";

export const teluguTranslations = {
  common: {
    appName: "FamilyKart AI",
  },
  languageSwitcher: {
    label: "భాష",
    english: "English",
    telugu: "తెలుగు",
  },
  home: {
    description: "ప్రతి కుటుంబానికి కలిసి షాపింగ్ చేయడం సులభం.",
    backendStatus: {
      label: "బ్యాక్‌ఎండ్ స్థితి",
      checking: "తనిఖీ చేస్తోంది...",
      connected: "కనెక్ట్ అయింది",
      unavailable: "అందుబాటులో లేదు",
      checkingAccessibilityLabel: "బ్యాక్‌ఎండ్ స్థితిని తనిఖీ చేస్తోంది",
    },
  },
  realtime: {
    normal: "తక్షణ నవీకరణలు సాధారణంగా ఆగిపోయాయి.",
    authenticationRequired: "మీ సెషన్ గడువు ముగిసింది. దయచేసి మళ్లీ సైన్ ఇన్ చేయండి.",
    householdUnavailable: "ఈ కుటుంబం ఇకపై మీ ఖాతాకు అందుబాటులో లేదు.",
    serviceUnavailable:
      "తక్షణ నవీకరణలు తాత్కాలికంగా అందుబాటులో లేవు. మళ్లీ కనెక్ట్ అవుతోంది.",
    connectionInterrupted:
      "తక్షణ కనెక్షన్‌కు అంతరాయం ఏర్పడింది. మళ్లీ కనెక్ట్ అవుతోంది.",
  },
  voice: {
    permission: {
      title: "మైక్రోఫోన్ అనుమతి",
      rationale:
        "వాయిస్ ద్వారా సరుకులను జోడించడానికి FamilyKart AIకి మైక్రోఫోన్ అనుమతి అవసరం.",
      request: "మైక్రోఫోన్‌ను అనుమతించండి",
      denied: "వాయిస్ ఇన్‌పుట్ ఉపయోగించడానికి మైక్రోఫోన్ అనుమతిని ఇవ్వండి.",
      blocked:
        "మైక్రోఫోన్ అనుమతి నిలిపివేయబడింది. వాయిస్ ఇన్‌పుట్ కోసం ఫోన్ సెట్టింగ్‌లలో అనుమతించండి.",
      openSettings: "సెట్టింగ్‌లు తెరవండి",
    },
    recorder: {
      title: "వాయిస్ కమాండ్",
      idle: "రికార్డ్ చేయడానికి సిద్ధంగా ఉంది",
      requestingPermission: "మైక్రోఫోన్ అనుమతిని తనిఖీ చేస్తోంది...",
      preparing: "మైక్రోఫోన్ సిద్ధమవుతోంది...",
      recording: "రికార్డ్ అవుతోంది",
      stopping: "రికార్డింగ్ పూర్తవుతోంది...",
      ready: "రికార్డింగ్ సిద్ధంగా ఉంది",
      failed: "రికార్డింగ్ విఫలమైంది. మళ్లీ ప్రయత్నించండి.",
      start: "రికార్డింగ్ ప్రారంభించండి",
      stop: "రికార్డింగ్ ఆపండి",
      cancel: "రికార్డింగ్ రద్దు చేయండి",
      recordAgain: "మళ్లీ రికార్డ్ చేయండి",
      durationAccessibility:
        "అనుమతించిన {{maximum}} సెకన్లలో {{seconds}} సెకన్లు రికార్డ్ అయ్యాయి",
    },
  },
} satisfies TranslationResources;
