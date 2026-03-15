import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  fetchCityStateCurrentStep,
  fetchCityStateNextStep,
  fetchWeatherCurrentStep,
  fetchWeatherNextStep,
} from "../data/api";
import { DisasterStepData, disasterStepsMock } from "../data/mock/disasterSteps";
import {
  CityStateStepResponse,
  InfoCategory,
  URGENCY_WEIGHT,
  WeatherDatasetMetadata,
  WeatherStepResponse,
} from "../data/types";

export interface StormState {
  center: { lat: number; lon: number };
  windRadiiKm: { r34: number; r50: number; r64: number };
  focusPoints: { name: string; lat: number; lon: number }[];
  movement: { direction_deg: number; speed_kmh: number } | null;
  radiusOfMaxWindKm: number;
  forecastNext: { lat: number; lon: number }[];
}

export interface AffectedArea {
  lat: number;
  lon: number;
  impact_type:
    | "flooding"
    | "road_closure"
    | "powerline_failure"
    | "debris"
    | "structure_damage";
  severity: number;
  danger_to_remain: string;
  status: string;
  radius_m: number;
}

interface StormZoneCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "Polygon"; coordinates: number[][][] };
    properties: { id: string; event: string; severity: string; region: string };
  }[];
}

interface DisasterDemoContextValue {
  currentStepIndex: number;
  totalSteps: number;
  currentStep: (typeof disasterStepsMock)[number];
  stepHistory: {
    stepIndex: number;
    step: (typeof disasterStepsMock)[number];
  }[];
  unreadBySection: (typeof disasterStepsMock)[number]["updateSummary"];
  unreadUpdates: number;
  isFinalStep: boolean;
  isStepping: boolean;
  weatherDatasetMetadata: WeatherDatasetMetadata | null;
  weatherZones: StormZoneCollection | null;
  stormState: StormState | null;
  cityAffectedAreas: AffectedArea[];
  latestHighRiskAlert: {
    stepIndex: number;
    title: string;
    urgency: string;
  } | null;
  disasterStarted: boolean;
  startDisaster: () => void;
  stepDisaster: (options?: { beautify?: boolean }) => Promise<void>;
  markSectionSeen: (
    section: keyof (typeof disasterStepsMock)[number]["updateSummary"],
  ) => void;
}

const DisasterDemoContext = createContext<DisasterDemoContextValue | undefined>(
  undefined,
);

function makeCircle(lat: number, lon: number, radiusKm: number): number[][] {
  const R = 6371;
  const steps = 64;
  const d = radiusKm / R;
  const latR = (lat * Math.PI) / 180;
  const lonR = (lon * Math.PI) / 180;
  const pts: number[][] = [];
  for (let i = 0; i <= steps; i++) {
    const brng = (2 * Math.PI * i) / steps;
    const pLat = Math.asin(
      Math.sin(latR) * Math.cos(d) +
        Math.cos(latR) * Math.sin(d) * Math.cos(brng),
    );
    const pLon =
      lonR +
      Math.atan2(
        Math.sin(brng) * Math.sin(d) * Math.cos(latR),
        Math.cos(d) - Math.sin(latR) * Math.sin(pLat),
      );
    pts.push([(pLon * 180) / Math.PI, (pLat * 180) / Math.PI]);
  }
  return pts;
}

function buildStormZones(
  raw: Record<string, unknown>,
): StormZoneCollection | null {
  const ss = raw.storm_state as any;
  if (!ss?.storm_center) return null;
  const { lat, lon } = ss.storm_center as { lat: number; lon: number };
  const radii = [
    { key: "r34", label: "34-kt wind radius", severity: "moderate" },
    { key: "r50", label: "50-kt wind radius", severity: "severe" },
    { key: "r64", label: "64-kt wind radius", severity: "extreme" },
  ] as const;
  const features = radii
    .filter(({ key }) => (ss.wind_radii_km?.[key] ?? 0) > 0)
    .map(({ key, label, severity }) => ({
      type: "Feature" as const,
      geometry: {
        type: "Polygon" as const,
        coordinates: [makeCircle(lat, lon, ss.wind_radii_km[key] as number)],
      },
      properties: {
        id: `storm-${key}`,
        event: label,
        severity,
        region: "Goma, DR Congo",
      },
    }));
  return features.length ? { type: "FeatureCollection", features } : null;
}

function applyWeatherPayloadToStep(
  step: (typeof disasterStepsMock)[number],
  weatherPayload: WeatherStepResponse,
): (typeof disasterStepsMock)[number] {
  const weatherUpdatedAt = weatherPayload.step.step_time;
  return {
    ...step,
    weather: weatherPayload.beautified.map((item) => ({
      ...item,
      updatedAt: weatherUpdatedAt,
    })),
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
  cityPayload: CityStateStepResponse,
): (typeof disasterStepsMock)[number] {
  const alertsUpdatedAt = cityPayload.step.step_time;
  return {
    ...step,
    alerts: cityPayload.alerts.map((item) => ({
      id: item.id,
      title: item.title,
      details: item.details,
      urgency: item.urgency,
      category: (item.category as InfoCategory) || "hazard update",
      occurredAt: item.occurredAt,
      updatedAt: item.updatedAt,
      area: item.area,
      status: item.status || item.source || "Active",
      lat: item.lat ?? undefined,
      lon: item.lon ?? undefined,
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

const EMPTY_STEP: DisasterStepData = {
  id: "step-idle",
  simulatedAt: new Date().toISOString(),
  alerts: [],
  evacuationPlans: [],
  connections: [],
  savedInformation: [],
  weather: [],
  sectionUpdatedAt: {
    alerts: "",
    evacuationPlans: "",
    connections: "",
    savedInformation: "",
    weather: "",
  },
  updateSummary: {
    alerts: 0,
    evacuationPlans: 0,
    connections: 0,
    savedInformation: 0,
    weather: 0,
  },
};

export function DisasterDemoProvider({ children }: { children: ReactNode }) {
  const [disasterStarted, setDisasterStarted] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [totalSteps, setTotalSteps] = useState(disasterStepsMock.length);
  const [stepHistory, setStepHistory] = useState<
    { stepIndex: number; step: (typeof disasterStepsMock)[number] }[]
  >([{ stepIndex: -1, step: EMPTY_STEP }]);
  const [unreadBySection, setUnreadBySection] = useState<
    (typeof disasterStepsMock)[number]["updateSummary"]
  >({
    alerts: 0,
    evacuationPlans: 0,
    connections: 0,
    savedInformation: 0,
    weather: 0,
  });
  const [latestHighRiskAlert, setLatestHighRiskAlert] = useState<{
    stepIndex: number;
    title: string;
    urgency: string;
  } | null>(null);
  const [isStepping, setIsStepping] = useState(false);
  const [weatherDatasetMetadata, setWeatherDatasetMetadata] =
    useState<WeatherDatasetMetadata | null>(null);
  const [currentStepRaw, setCurrentStepRaw] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [currentCityStateRaw, setCurrentCityStateRaw] = useState<Record<
    string,
    unknown
  > | null>(null);
  const currentStep =
    stepHistory[stepHistory.length - 1]?.step ?? EMPTY_STEP;
  const isFinalStep = currentStepIndex >= totalSteps - 1;
  const unreadUpdates = Object.values(unreadBySection).reduce(
    (sum, count) => sum + count,
    0,
  );

  useEffect(() => {
    if (!disasterStarted) return;

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
        setCurrentStepRaw(weatherPayload.raw as Record<string, unknown>);
        setCurrentCityStateRaw(cityPayload.raw as Record<string, unknown>);
        setTotalSteps(cityPayload.step.total_steps);
        if (weatherPayload.step.total_steps !== cityPayload.step.total_steps) {
          console.warn(
            "Weather and city-state step totals differ:",
            weatherPayload.step.total_steps,
            cityPayload.step.total_steps,
          );
        }
        setCurrentStepIndex(0);
        setStepHistory((previous) => {
          if (previous.length === 0) {
            return previous;
          }
          const baseMockStep = disasterStepsMock[0];
          const weatherPatched = applyWeatherPayloadToStep(
            baseMockStep,
            weatherPayload,
          );
          const updatedInitialStep = applyCityStatePayloadToStep(
            weatherPatched,
            cityPayload,
          );
          // Inject the emergency warning alert at the top of step 0
          const now = new Date().toISOString();
          const emergencyAlert = {
            id: "emergency-warning-0",
            title: "Severe typhoon warning. Extreme flooding warning.",
            details:
              "Please follow your evacuation instructions to get to safety as soon as possible, we are coordinating with your connections.",
            urgency: "extreme urgency alert" as const,
            category: "evacuation" as const,
            occurredAt: now,
            updatedAt: now,
            area: "Vilankulo, Mozambique",
            status: "Emergency",
          };
          const stepWithAlert = {
            ...updatedInitialStep,
            alerts: [emergencyAlert, ...updatedInitialStep.alerts],
            updateSummary: {
              ...updatedInitialStep.updateSummary,
              alerts: updatedInitialStep.updateSummary.alerts + 1,
            },
          };
          return [
            { stepIndex: 0, step: stepWithAlert },
            ...previous.slice(1),
          ];
        });
      } catch (err) {
        console.error(
          "[DisasterDemo] Failed to load initial weather step:",
          err,
        );
      }
    }

    void loadInitialWeatherStep();

    return () => {
      cancelled = true;
    };
  }, [disasterStarted]);

  const weatherZones = useMemo(
    () => (currentStepRaw ? buildStormZones(currentStepRaw) : null),
    [currentStepRaw],
  );

  const stormState = useMemo<StormState | null>(() => {
    const ss = currentStepRaw?.storm_state as any;
    if (!ss?.storm_center) return null;
    return {
      center: ss.storm_center,
      windRadiiKm: {
        r34: ss.wind_radii_km?.r34 ?? 0,
        r50: ss.wind_radii_km?.r50 ?? 0,
        r64: ss.wind_radii_km?.r64 ?? 0,
      },
      focusPoints: Array.isArray(ss.focus_points) ? ss.focus_points : [],
      movement: ss.movement ?? null,
      radiusOfMaxWindKm: ss.radius_of_maximum_wind_km ?? 0,
      forecastNext: Object.values(ss.forecast_next ?? {})
        .map((f: any) => f?.storm_center)
        .filter((c: any) => c?.lat !== undefined && c?.lon !== undefined) as { lat: number; lon: number }[],
    };
  }, [currentStepRaw]);

  const cityAffectedAreas = useMemo<AffectedArea[]>(() => {
    const areas = (currentCityStateRaw?.city_state as any)?.affected_areas;
    return Array.isArray(areas) ? (areas as AffectedArea[]) : [];
  }, [currentCityStateRaw]);

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
      disasterStarted,
      startDisaster: () => setDisasterStarted(true),
      weatherDatasetMetadata,
      weatherZones,
      stormState,
      cityAffectedAreas,
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
        const baseNextStep =
          disasterStepsMock[Math.min(nextIndex, disasterStepsMock.length - 1)];
        let resolvedNextStep = { ...baseNextStep };

        try {
          const [weatherPayload, cityPayload] = await Promise.all([
            fetchWeatherNextStep(currentStepIndex, beautify),
            fetchCityStateNextStep(currentStepIndex, beautify),
          ]);
          setWeatherDatasetMetadata(weatherPayload.metadata);
          setCurrentStepRaw(weatherPayload.raw as Record<string, unknown>);
          setCurrentCityStateRaw(cityPayload.raw as Record<string, unknown>);
          setTotalSteps(cityPayload.step.total_steps);
          const weatherPatched = applyWeatherPayloadToStep(
            baseNextStep,
            weatherPayload,
          );
          resolvedNextStep = applyCityStatePayloadToStep(
            weatherPatched,
            cityPayload,
          );
        } catch (err) {
          console.error("[DisasterDemo] Failed to fetch next step:", err);
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
            previousUnread.evacuationPlans +
            resolvedNextStep.updateSummary.evacuationPlans,
          connections:
            previousUnread.connections +
            resolvedNextStep.updateSummary.connections,
          savedInformation:
            previousUnread.savedInformation +
            resolvedNextStep.updateSummary.savedInformation,
          weather:
            previousUnread.weather + resolvedNextStep.updateSummary.weather,
        }));

        const topHighRiskAlert = [...resolvedNextStep.alerts]
          .sort(
            (left, right) =>
              URGENCY_WEIGHT[right.urgency] - URGENCY_WEIGHT[left.urgency],
          )
          .find(
            (alert) => URGENCY_WEIGHT[alert.urgency] > URGENCY_WEIGHT.warning,
          );

        if (topHighRiskAlert) {
          setLatestHighRiskAlert({
            stepIndex: nextIndex,
            title: topHighRiskAlert.title,
            urgency: topHighRiskAlert.urgency,
          });
        }
      },
      markSectionSeen: (section) => {
        setUnreadBySection((previousUnread) => ({
          ...previousUnread,
          [section]: 0,
        }));
      },
    }),
    [
      currentStep,
      currentStepIndex,
      totalSteps,
      isStepping,
      disasterStarted,
      isFinalStep,
      latestHighRiskAlert,
      stepHistory,
      weatherDatasetMetadata,
      weatherZones,
      stormState,
      cityAffectedAreas,
      unreadBySection,
      unreadUpdates,
    ],
  );

  return (
    <DisasterDemoContext.Provider value={value}>
      {children}
    </DisasterDemoContext.Provider>
  );
}

export function useDisasterDemo() {
  const context = useContext(DisasterDemoContext);

  if (!context) {
    throw new Error(
      "useDisasterDemo must be used inside a DisasterDemoProvider",
    );
  }

  return context;
}
