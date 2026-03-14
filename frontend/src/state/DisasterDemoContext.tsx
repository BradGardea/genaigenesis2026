import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import {
  fetchCityStateCurrentStep,
  fetchCityStateNextStep,
  fetchWeatherCurrentStep,
  fetchWeatherNextStep,
} from "../data/api";
import { disasterStepsMock } from "../data/mock/disasterSteps";
import {
  CityStateStepResponse,
  URGENCY_WEIGHT,
  WeatherDatasetMetadata,
  WeatherStepResponse,
} from "../data/types";

interface DisasterDemoContextValue {
  currentStepIndex: number;
  totalSteps: number;
  currentStep: (typeof disasterStepsMock)[number];
  stepHistory: { stepIndex: number; step: (typeof disasterStepsMock)[number] }[];
  unreadBySection: (typeof disasterStepsMock)[number]["updateSummary"];
  unreadUpdates: number;
  isFinalStep: boolean;
  isStepping: boolean;
  weatherDatasetMetadata: WeatherDatasetMetadata | null;
  latestHighRiskAlert: { stepIndex: number; title: string; urgency: string } | null;
  stepDisaster: (options?: { beautify?: boolean }) => Promise<void>;
  markSectionSeen: (section: keyof (typeof disasterStepsMock)[number]["updateSummary"]) => void;
}

const DisasterDemoContext = createContext<DisasterDemoContextValue | undefined>(undefined);

function applyWeatherPayloadToStep(
  step: (typeof disasterStepsMock)[number],
  weatherPayload: WeatherStepResponse
): (typeof disasterStepsMock)[number] {
  const weatherUpdatedAt = weatherPayload.step.step_time;
  return {
    ...step,
    weather: weatherPayload.beautified.map((item) => ({ ...item, updatedAt: weatherUpdatedAt })),
    sectionUpdatedAt: {
      ...step.sectionUpdatedAt,
      weather: weatherUpdatedAt,
    },
    updateSummary: {
      ...step.updateSummary,
      weather: weatherPayload.beautified.length,
    },
    simulatedAt: weatherUpdatedAt,
  };
}

function applyCityStatePayloadToStep(
  step: (typeof disasterStepsMock)[number],
  cityPayload: CityStateStepResponse
): (typeof disasterStepsMock)[number] {
  const alertsUpdatedAt = cityPayload.step.step_time;
  return {
    ...step,
    alerts: cityPayload.alerts.map((item) => ({
      id: item.id,
      title: item.title,
      details: item.details,
      urgency: item.urgency,
      category: "hazard update",
      occurredAt: item.occurredAt,
      updatedAt: item.updatedAt,
      area: item.area,
      source: item.source,
    })),
    sectionUpdatedAt: {
      ...step.sectionUpdatedAt,
      alerts: alertsUpdatedAt,
    },
    updateSummary: {
      ...step.updateSummary,
      alerts: cityPayload.alerts.length,
    },
    cityStateRaw: cityPayload.raw,
    cityStateBeautified: cityPayload.beautified.map((item) => ({ ...item })),
  };
}

export function DisasterDemoProvider({ children }: { children: ReactNode }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [totalSteps, setTotalSteps] = useState(disasterStepsMock.length);
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
  const [isStepping, setIsStepping] = useState(false);
  const [weatherDatasetMetadata, setWeatherDatasetMetadata] = useState<WeatherDatasetMetadata | null>(null);
  const currentStep = stepHistory[stepHistory.length - 1]?.step ?? disasterStepsMock[0];
  const isFinalStep = currentStepIndex >= totalSteps - 1;
  const unreadUpdates = Object.values(unreadBySection).reduce((sum, count) => sum + count, 0);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialWeatherStep() {
      try {
        const [weatherPayload, cityPayload] = await Promise.all([
          fetchWeatherCurrentStep(0),
          fetchCityStateCurrentStep(0),
        ]);
        if (cancelled) {
          return;
        }

        setWeatherDatasetMetadata(weatherPayload.metadata);
        setTotalSteps(cityPayload.step.total_steps);
        if (weatherPayload.step.total_steps !== cityPayload.step.total_steps) {
          console.warn(
            "Weather and city-state step totals differ:",
            weatherPayload.step.total_steps,
            cityPayload.step.total_steps
          );
        }
        setStepHistory((previous) => {
          if (previous.length === 0) {
            return previous;
          }
          const initial = previous[0];
          const weatherPatched = applyWeatherPayloadToStep(initial.step, weatherPayload);
          const updatedInitialStep = applyCityStatePayloadToStep(weatherPatched, cityPayload);
          return [{ stepIndex: 0, step: updatedInitialStep }, ...previous.slice(1)];
        });
      } catch {
        // Keep local mocks when dataset endpoints are unavailable.
      }
    }

    void loadInitialWeatherStep();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<DisasterDemoContextValue>(
    () => ({
      currentStepIndex,
      totalSteps,
      currentStep,
      stepHistory,
      unreadBySection,
      unreadUpdates,
      isFinalStep,
      isStepping,
      weatherDatasetMetadata,
      latestHighRiskAlert,
      stepDisaster: async (options) => {
        if (isStepping) {
          return;
        }
        const beautify = options?.beautify ?? true;

        const nextIndex = Math.min(currentStepIndex + 1, totalSteps - 1);
        if (nextIndex === currentStepIndex) {
          return;
        }

        setIsStepping(true);
        const baseNextStep = disasterStepsMock[Math.min(nextIndex, disasterStepsMock.length - 1)];
        let resolvedNextStep = { ...baseNextStep };

        try {
          const [weatherPayload, cityPayload] = await Promise.all([
            fetchWeatherNextStep(currentStepIndex, beautify),
            fetchCityStateNextStep(currentStepIndex, beautify),
          ]);
          setWeatherDatasetMetadata(weatherPayload.metadata);
          setTotalSteps(cityPayload.step.total_steps);
          const weatherPatched = applyWeatherPayloadToStep(baseNextStep, weatherPayload);
          resolvedNextStep = applyCityStatePayloadToStep(weatherPatched, cityPayload);
        } catch {
          resolvedNextStep = { ...baseNextStep };
        } finally {
          setIsStepping(false);
        }

        setCurrentStepIndex(nextIndex);
        setStepHistory((previousHistory) => [
          ...previousHistory,
          { stepIndex: nextIndex, step: resolvedNextStep },
        ]);
        setUnreadBySection((previousUnread) => ({
          alerts: previousUnread.alerts + resolvedNextStep.updateSummary.alerts,
          evacuationPlans:
            previousUnread.evacuationPlans + resolvedNextStep.updateSummary.evacuationPlans,
          connections: previousUnread.connections + resolvedNextStep.updateSummary.connections,
          savedInformation:
            previousUnread.savedInformation + resolvedNextStep.updateSummary.savedInformation,
          weather: previousUnread.weather + resolvedNextStep.updateSummary.weather,
        }));

        const topHighRiskAlert = [...resolvedNextStep.alerts]
          .sort((left, right) => URGENCY_WEIGHT[right.urgency] - URGENCY_WEIGHT[left.urgency])
          .find((alert) => URGENCY_WEIGHT[alert.urgency] > URGENCY_WEIGHT.warning);

        if (topHighRiskAlert) {
          setLatestHighRiskAlert({
            stepIndex: nextIndex,
            title: topHighRiskAlert.title,
            urgency: topHighRiskAlert.urgency,
          });
        }
      },
      markSectionSeen: (section) => {
        setUnreadBySection((previousUnread) => ({ ...previousUnread, [section]: 0 }));
      },
    }),
    [
      currentStep,
      currentStepIndex,
      totalSteps,
      isStepping,
      isFinalStep,
      latestHighRiskAlert,
      stepHistory,
      weatherDatasetMetadata,
      unreadBySection,
      unreadUpdates,
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
