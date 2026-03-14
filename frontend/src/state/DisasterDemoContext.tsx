import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import { disasterStepsMock } from "../data/mock/disasterSteps";
import { URGENCY_WEIGHT } from "../data/types";

interface DisasterDemoContextValue {
  currentStepIndex: number;
  totalSteps: number;
  currentStep: (typeof disasterStepsMock)[number];
  stepHistory: { stepIndex: number; step: (typeof disasterStepsMock)[number] }[];
  unreadBySection: (typeof disasterStepsMock)[number]["updateSummary"];
  unreadUpdates: number;
  isFinalStep: boolean;
  latestHighRiskAlert: { stepIndex: number; title: string; urgency: string } | null;
  stepDisaster: () => void;
  markSectionSeen: (section: keyof (typeof disasterStepsMock)[number]["updateSummary"]) => void;
}

const DisasterDemoContext = createContext<DisasterDemoContextValue | undefined>(undefined);

export function DisasterDemoProvider({ children }: { children: ReactNode }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepHistory, setStepHistory] = useState<{ stepIndex: number; step: (typeof disasterStepsMock)[number] }[]>([
    { stepIndex: 0, step: disasterStepsMock[0] }
  ]);
  const [unreadBySection, setUnreadBySection] = useState<(typeof disasterStepsMock)[number]["updateSummary"]>({
    alerts: 0,
    evacuationPlans: 0,
    connections: 0,
    savedInformation: 0,
    weather: 0
  });
  const [latestHighRiskAlert, setLatestHighRiskAlert] = useState<{
    stepIndex: number;
    title: string;
    urgency: string;
  } | null>(null);

  const currentStep = disasterStepsMock[currentStepIndex];
  const isFinalStep = currentStepIndex >= disasterStepsMock.length - 1;
  const unreadUpdates = Object.values(unreadBySection).reduce((sum, count) => sum + count, 0);

  const value = useMemo<DisasterDemoContextValue>(
    () => ({
      currentStepIndex,
      totalSteps: disasterStepsMock.length,
      currentStep,
      stepHistory,
      unreadBySection,
      unreadUpdates,
      isFinalStep,
      latestHighRiskAlert,
      stepDisaster: () => {
        setCurrentStepIndex((previousIndex) => {
          const nextIndex = Math.min(previousIndex + 1, disasterStepsMock.length - 1);

          if (nextIndex !== previousIndex) {
            const nextStep = disasterStepsMock[nextIndex];
            setStepHistory((previousHistory) => [...previousHistory, { stepIndex: nextIndex, step: nextStep }]);
            setUnreadBySection((previousUnread) => ({
              alerts: previousUnread.alerts + nextStep.updateSummary.alerts,
              evacuationPlans: previousUnread.evacuationPlans + nextStep.updateSummary.evacuationPlans,
              connections: previousUnread.connections + nextStep.updateSummary.connections,
              savedInformation: previousUnread.savedInformation + nextStep.updateSummary.savedInformation,
              weather: previousUnread.weather + nextStep.updateSummary.weather
            }));

            const topHighRiskAlert = [...nextStep.alerts]
              .sort((left, right) => URGENCY_WEIGHT[right.urgency] - URGENCY_WEIGHT[left.urgency])
              .find((alert) => URGENCY_WEIGHT[alert.urgency] > URGENCY_WEIGHT.warning);

            if (topHighRiskAlert) {
              setLatestHighRiskAlert({
                stepIndex: nextIndex,
                title: topHighRiskAlert.title,
                urgency: topHighRiskAlert.urgency
              });
            }
          }

          return nextIndex;
        });
      },
      markSectionSeen: (section) => {
        setUnreadBySection((previousUnread) => ({ ...previousUnread, [section]: 0 }));
      }
    }),
    [
      currentStep,
      currentStepIndex,
      isFinalStep,
      latestHighRiskAlert,
      stepHistory,
      unreadBySection,
      unreadUpdates
    ]
  );

  return <DisasterDemoContext.Provider value={value}>{children}</DisasterDemoContext.Provider>;
}

export function useDisasterDemo() {
  const context = useContext(DisasterDemoContext);

  if (!context) {
    throw new Error("useDisasterDemo must be used inside a DisasterDemoProvider");
  }

  return context;
}
