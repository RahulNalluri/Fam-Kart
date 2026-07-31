import { useCallback, useState } from "react";

import { RealtimeCloseOutcome } from "../services/realtime";

export type RealtimeStatusNoticeState = {
  outcome: RealtimeCloseOutcome | null;
  showOutcome: (outcome: RealtimeCloseOutcome) => void;
  handleRecovered: () => void;
  clearOutcome: () => void;
};

export function useRealtimeStatusNotice(): RealtimeStatusNoticeState {
  const [outcome, setOutcome] = useState<RealtimeCloseOutcome | null>(null);

  const showOutcome = useCallback((nextOutcome: RealtimeCloseOutcome) => {
    setOutcome(nextOutcome);
  }, []);

  const handleRecovered = useCallback(() => {
    setOutcome((currentOutcome) => (currentOutcome?.retryable ? null : currentOutcome));
  }, []);

  const clearOutcome = useCallback(() => {
    setOutcome(null);
  }, []);

  return { outcome, showOutcome, handleRecovered, clearOutcome };
}
