import { useEffect, useMemo, useState } from "react";
import { FlatList, Image, Modal, Pressable, Text, View } from "react-native";
import {
  DISASTER_STEP_INTERVAL_MINUTES,
  EvacuationPlan,
  InfoBubble,
  disasterStepsMock,
  fetchFirstPersonConnections,
  URGENCY_CARD_COLORS,
  URGENCY_WEIGHT,
} from "../data";
import {
  PersonConnectionsResponse,
  PersonConnectionNode,
  PersonSummary,
  SavedDocType,
  WeatherConditionType,
} from "../data/types";
import { useDisasterDemo } from "../state/DisasterDemoContext";
import { AppTheme } from "../types/theme";
import VoiceWidget from "@/components/Audio";
import logoGreenBlue from "../assets/logos/crisis-net-logo-green-blue.png";

type InfoSection =
  | "alerts"
  | "evacuation plans"
  | "my connections"
  | "saved information"
  | "weather";

interface InfoScreenProps {
  theme: AppTheme;
}

const SECTION_OPTIONS: InfoSection[] = [
  "alerts",
  "evacuation plans",
  "my connections",
  "saved information",
  "weather"
];

const URGENCY_PILL_TEXT_COLOR: Record<string, Record<AppTheme, string>> = {
  notification: { light: "#0369a1", dark: "#bae6fd" },
  caution: { light: "#a16207", dark: "#fde68a" },
  warning: { light: "#c2410c", dark: "#fed7aa" },
  "urgent warning": { light: "#9a3412", dark: "#fdba74" },
  alert: { light: "#b91c1c", dark: "#fecaca" },
  "urgent alert": { light: "#991b1b", dark: "#fca5a5" },
  "extreme urgency alert": { light: "#7f1d1d", dark: "#ef4444" }
};

function formatTime(dateValue: string): string {
  return new Date(dateValue).toLocaleString();
}

function toSectionTitle(section: InfoSection): string {
  return section
    .split(" ")
    .map((word) => `${word[0].toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function toSectionUpdatedAtKey(section: InfoSection): keyof (typeof disasterStepsMock)[number]["sectionUpdatedAt"] {
  if (section === "evacuation plans") {
    return "evacuationPlans";
  }

  if (section === "my connections") {
    return "connections";
  }

  if (section === "saved information") {
    return "savedInformation";
  }

  return section;
}

const urgencyToken = (urgency: string): string => {
  switch (urgency) {
    case "urgent warning":
      return "urgentWarning";
    case "urgent alert":
      return "urgentAlert";
    case "extreme urgency alert":
      return "extremeUrgency";
    default:
      return urgency.replace(/\s+/g, "");
  }
};

export function InfoScreen({ theme }: InfoScreenProps) {
  const isDark = theme === "dark";
  const {
    currentStepIndex,
    totalSteps,
    stepHistory,
    unreadBySection,
    unreadUpdates,
    markSectionSeen
  } = useDisasterDemo();
  const [menuOpen, setMenuOpen] = useState(false);
  const [section, setSection] = useState<InfoSection>("alerts");
  const [connectionsPayload, setConnectionsPayload] = useState<PersonConnectionsResponse | null>(null);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const stepHistoryNewestFirst = useMemo(
    () => [...stepHistory].filter(({ stepIndex }) => stepIndex >= 0).reverse(),
    [stepHistory],
  );
  const latestStep = stepHistory[stepHistory.length - 1]?.step ?? disasterStepsMock[0];
  const referenceNowMs = new Date(latestStep.simulatedAt).getTime();

  const commonCardClass = `mb-3 rounded-xl border p-4 ${
    isDark ? "border-brand-darkBorder bg-brand-darkCard" : "border-brand-border bg-brand-card shadow-soft"
  }`;

  const getFreshnessColor = (isoTime: string): string => {
    const ageMinutes = Math.max(0, (referenceNowMs - new Date(isoTime).getTime()) / 60000);
    if (ageMinutes <= 5) return "text-status-success";
    if (ageMinutes <= 10) return "text-status-warn";
    return "text-status-danger";
  };

  const renderAlerts = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => {
        const isCurrentBlock = stepIndex === currentStepIndex;
        const sortedAlerts: InfoBubble[] = [...step.alerts].sort((left, right) => {
          const urgencyDiff = URGENCY_WEIGHT[right.urgency] - URGENCY_WEIGHT[left.urgency];

          if (urgencyDiff !== 0) {
            return urgencyDiff;
          }

          return new Date(right.occurredAt).getTime() - new Date(left.occurredAt).getTime();
        });

        return (
          <View key={`alerts-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
            <Text
              className={`text-xs font-semibold uppercase ${getFreshnessColor(step.sectionUpdatedAt.alerts)}`}
            >
              Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.alerts)}
            </Text>
            {sortedAlerts.map((item) => {
              const token = urgencyToken(item.urgency);
              const accentBg = `bg-urgency-${token}-${isDark ? "darkBg" : "lightBg"}`;
              const accentBorder = `bg-urgency-${token}-${isDark ? "darkBorder" : "lightBorder"}`;
              const pillText = URGENCY_PILL_TEXT_COLOR[item.urgency][theme];

              return (
                <View key={`alerts-step-${stepIndex}-${item.id}`} className="relative mt-3">
                  <View className={`absolute left-0 top-0 bottom-0 w-1.5 rounded-full ${accentBorder}`} />
                  <View
                    className={`ml-2 rounded-xl border px-4 pb-4 pt-3 ${
                      isDark
                        ? "border-brand-darkBorder bg-brand-darkCard shadow-panel"
                        : "border-brand-border bg-brand-card shadow-soft"
                    }`}
                  >
                    <View className="mb-3 flex-row items-center justify-between">
                      <View className={`rounded-pill px-3 py-1 ${accentBg}`}>
                        <Text className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: pillText }}>
                          {item.urgency}
                        </Text>
                      </View>
                      <View
                        className={`rounded-md px-2 py-0.5 ${
                          item.category === "advisory"
                            ? isDark ? "bg-sky-900/60" : "bg-sky-100"
                            : item.category === "closure"
                              ? isDark ? "bg-amber-900/60" : "bg-amber-100"
                              : isDark ? "bg-rose-900/40" : "bg-rose-100"
                        }`}
                      >
                        <Text
                          className={`text-[11px] font-semibold capitalize ${
                            item.category === "advisory"
                              ? isDark ? "text-sky-300" : "text-sky-700"
                              : item.category === "closure"
                                ? isDark ? "text-amber-300" : "text-amber-700"
                                : isDark ? "text-rose-300" : "text-rose-700"
                          }`}
                        >
                          {item.category}
                        </Text>
                      </View>
                    </View>

                    <Text className={`text-base font-semibold ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}>
                      {item.title}
                    </Text>
                    <Text className={`mb-3 mt-1 text-sm leading-6 ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}>
                      {item.details}
                    </Text>

                    <View
                      className={`rounded-lg border px-3 py-3 ${
                        isDark
                          ? "border-brand-darkBorder bg-brand-darkSurface"
                          : "border-brand-border bg-brand-surface"
                      }`}
                    >
                      <View className="flex-row items-center justify-between">
                        <Text className={`text-xs ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
                          {item.area}{item.lat != null && item.lon != null ? ` (${item.lat.toFixed(3)}, ${item.lon.toFixed(3)})` : ""}
                        </Text>
                        <View className="flex-row items-center">
                          <View
                            className={`mr-1.5 h-2 w-2 rounded-full ${
                              item.status === "Critical" || item.status === "Worsening"
                                ? "bg-red-500"
                                : item.status === "Active" || item.status === "Intensifying"
                                  ? "bg-amber-500"
                                  : item.status === "Easing" || item.status === "Persisting"
                                    ? "bg-yellow-400"
                                    : "bg-emerald-500"
                            }`}
                          />
                          <Text className={`text-xs font-medium ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
                            {item.status}
                          </Text>
                        </View>
                      </View>
                      <Text className={`mt-1 text-xs ${getFreshnessColor(item.occurredAt)}`}>
                        Occurred: {formatTime(item.occurredAt)}
                      </Text>
                    </View>
                  </View>
                </View>
              );
            })}
            {!isCurrentBlock ? (
              <View
                pointerEvents="none"
                className="absolute inset-0 rounded-2xl"
                style={{ backgroundColor: isDark ? "rgba(100,116,139,0.34)" : "rgba(148,163,184,0.28)" }}
              />
            ) : null}
          </View>
        );
      })}
    </View>
  );

  const renderPlans = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => {
        const isCurrentBlock = stepIndex === currentStepIndex;
        const sortedPlans: EvacuationPlan[] = [...step.evacuationPlans].sort(
          (left, right) => right.successProbability - left.successProbability
        );

        return (
          <View key={`plans-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
            <Text
              className={`text-xs font-semibold uppercase ${getFreshnessColor(step.sectionUpdatedAt.evacuationPlans)}`}
            >
              Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.evacuationPlans)}
            </Text>
            {sortedPlans.map((item) => (
              <View key={`plans-step-${stepIndex}-${item.id}`} className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
                <View className="mb-2 flex-row items-center justify-between">
                  <Text className={`mr-3 flex-1 text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                    {item.title}
                  </Text>
                  <View className={`rounded-full px-3 py-1 ${isDark ? "bg-emerald-800" : "bg-emerald-100"}`}>
                    <Text className={`text-xs font-semibold ${isDark ? "text-emerald-100" : "text-emerald-700"}`}>
                      {item.successProbability}% success
                    </Text>
                  </View>
                </View>
                <Text className={`mb-3 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.summary}</Text>
                <Text className={`mb-1 text-xs font-semibold uppercase ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                  Steps
                </Text>
                {item.steps.map((planStep, index) => (
                  <Text
                    key={`plans-step-${stepIndex}-${item.id}-step-${index + 1}`}
                    className={`mb-1 text-sm ${isDark ? "text-slate-200" : "text-slate-800"}`}
                  >
                    {index + 1}. {planStep}
                  </Text>
                ))}
                <Text className={`mb-1 mt-3 text-xs font-semibold uppercase ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                  Pack if possible
                </Text>
                {item.packingList.map((entry, index) => (
                  <Text
                    key={`plans-step-${stepIndex}-${item.id}-pack-${index + 1}`}
                    className={`mb-1 text-sm ${isDark ? "text-slate-200" : "text-slate-800"}`}
                  >
                    - {entry}
                  </Text>
                ))}
                {item.updatedAt ? (
                  <Text className={`mt-2 text-xs ${getFreshnessColor(item.updatedAt)}`}>
                    Updated: {formatTime(item.updatedAt)}
                  </Text>
                ) : null}
              </View>
            ))}
            {!isCurrentBlock ? (
              <View
                pointerEvents="none"
                className="absolute inset-0 rounded-2xl"
                style={{ backgroundColor: isDark ? "rgba(100,116,139,0.34)" : "rgba(148,163,184,0.28)" }}
              />
            ) : null}
          </View>
        );
      })}
    </View>
  );

  useEffect(() => {
    if (connectionsPayload || connectionsLoading) return;
    setConnectionsLoading(true);
    fetchFirstPersonConnections()
      .then(setConnectionsPayload)
      .catch((error: unknown) => {
        setConnectionsError(error instanceof Error ? error.message : "Failed to load connections");
      })
      .finally(() => setConnectionsLoading(false));
  }, [connectionsPayload, connectionsLoading]);

  const renderPersonCard = (title: string, person: PersonSummary, accent?: string) => (
    <View className={`mt-3 rounded-xl p-4 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
      <Text className={`text-xs font-semibold uppercase ${accent ?? (isDark ? "text-slate-300" : "text-slate-600")}`}>
        {title}
      </Text>
      <Text className={`mt-1 text-lg font-semibold ${isDark ? "text-slate-50" : "text-slate-900"}`}>
        {person.name}
      </Text>
      <Text className={`mt-1 text-sm ${isDark ? "text-slate-200" : "text-slate-700"}`}>
        Scenario: {person.scenario}
      </Text>
      <Text className={`mt-1 text-sm ${isDark ? "text-slate-200" : "text-slate-700"}`}>
        Seats available: {person.seats_available}
      </Text>
      <Text className={`mt-1 text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
        Position: {person.current_position[1].toFixed(3)}, {person.current_position[0].toFixed(3)}
      </Text>
    </View>
  );

  const renderConnections = () => {
    const updatedAt = connectionsPayload?.metadata.generated_at ?? latestStep.sectionUpdatedAt.connections;

    return (
      <View>
        <View className={`${commonCardClass} relative overflow-hidden`}>
          <Text className={`text-xs font-semibold uppercase ${getFreshnessColor(updatedAt)}`}>
            Updated {formatTime(updatedAt)}
          </Text>

          {connectionsLoading ? (
            <Text className={`mt-3 ${isDark ? "text-slate-300" : "text-slate-700"}`}>Loading connections…</Text>
          ) : connectionsError ? (
            <Text className="mt-3 text-status-danger">Error: {connectionsError}</Text>
          ) : connectionsPayload ? (
            <>
              {renderPersonCard("You", connectionsPayload.focal_person, isDark ? "text-emerald-200" : "text-emerald-700")}
              <Text className={`mt-4 text-sm font-semibold uppercase ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                Connections ({connectionsPayload.connections.length})
              </Text>
              {connectionsPayload.connections.length === 0 ? (
                <Text className={`mt-2 ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                  No connections found in the graph.
                </Text>
              ) : (
                connectionsPayload.connections.map((node: PersonConnectionNode, index: number) => (
                  <View
                    key={`connection-${node.person.person_id}-${index}`}
                    className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-900" : "bg-white"}`}
                  >
                    <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                      {node.person.name}
                    </Text>
                    <Text className={`mt-1 text-sm capitalize ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                      Relationship: {node.relationship}
                    </Text>
                    <Text className={`mt-1 text-sm ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                      Seats available: {node.person.seats_available}
                    </Text>
                    <Text className={`mt-1 text-sm ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                      Scenario: {node.person.scenario}
                    </Text>
                    <Text className={`mt-1 text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
                      Position: {node.person.current_position[1].toFixed(3)}, {node.person.current_position[0].toFixed(3)}
                    </Text>
                  </View>
                ))
              )}
            </>
          ) : (
            <Text className={`mt-3 ${isDark ? "text-slate-300" : "text-slate-700"}`}>No data available.</Text>
          )}
        </View>
      </View>
    );
  };

  const docGlyph = (docType?: SavedDocType): string => {
    switch (docType) {
      case "map": return "🗺️";
      case "guide": return "📘";
      case "shelter_list": return "🏠";
      case "signal_guide": return "📡";
      case "contacts": return "📞";
      case "checklist": return "☑️";
      case "water_safety": return "💧";
      case "first_aid": return "🩹";
      default: return "📄";
    }
  };

  const allSavedDocs = useMemo(() => {
    const docs: typeof latestStep.savedInformation = [];
    for (const { step } of stepHistory) {
      for (const doc of step.savedInformation) {
        if (!docs.some((d) => d.id === doc.id)) {
          docs.push(doc);
        }
      }
    }
    return docs;
  }, [stepHistory]);

  const renderSavedInformation = () => (
    <View>
      {allSavedDocs.length === 0 ? (
        <View className={commonCardClass}>
          <Text className={`text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>
            No offline resources downloaded yet. Documents will be fetched automatically.
          </Text>
        </View>
      ) : (
        <View className={commonCardClass}>
          <View className="flex-row items-center justify-between">
            <Text className={`text-xs font-semibold uppercase ${isDark ? "text-emerald-400" : "text-emerald-600"}`}>
              Offline Resources
            </Text>
            <View className={`rounded-md px-2 py-0.5 ${isDark ? "bg-emerald-900/50" : "bg-emerald-100"}`}>
              <Text className={`text-[10px] font-semibold ${isDark ? "text-emerald-300" : "text-emerald-700"}`}>
                {allSavedDocs.length} documents
              </Text>
            </View>
          </View>
          {allSavedDocs.map((item) => (
            <View
              key={`saved-${item.id}`}
              className={`mt-3 flex-row rounded-xl border p-3 ${
                isDark ? "border-brand-darkBorder bg-brand-darkSurface" : "border-brand-border bg-brand-surface"
              }`}
            >
              <View
                className={`mr-3 h-10 w-10 items-center justify-center rounded-lg ${
                  isDark ? "bg-slate-700" : "bg-slate-200"
                }`}
              >
                <Text className="text-lg">{docGlyph(item.docType)}</Text>
              </View>
              <View className="flex-1">
                <View className="flex-row items-start justify-between">
                  <Text
                    className={`flex-1 text-sm font-semibold ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}
                  >
                    {item.title}
                  </Text>
                  {item.offline ? (
                    <View className="ml-2 flex-row items-center">
                      <View className="mr-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      <Text className={`text-[10px] font-medium ${isDark ? "text-emerald-400" : "text-emerald-600"}`}>
                        Offline
                      </Text>
                    </View>
                  ) : null}
                </View>
                <Text
                  className={`mt-1 text-xs leading-5 ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}
                  numberOfLines={3}
                >
                  {item.note}
                </Text>
                <View className="mt-2 flex-row items-center">
                  {item.fileSize ? (
                    <View
                      className={`mr-2 rounded px-1.5 py-0.5 ${isDark ? "bg-slate-700" : "bg-slate-200"}`}
                    >
                      <Text className={`text-[10px] font-medium ${isDark ? "text-slate-300" : "text-slate-600"}`}>
                        {item.fileSize}
                      </Text>
                    </View>
                  ) : null}
                  <Text className={`text-[10px] ${isDark ? "text-slate-500" : "text-slate-400"}`}>
                    {formatTime(item.updatedAt)}
                  </Text>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );

  const weatherGlyph = (conditionType?: WeatherConditionType): string => {
    switch (conditionType) {
      case "cyclone": return "\uD83C\uDF00";
      case "thunderstorm": return "\u26C8\uFE0F";
      case "heavy_rain": return "\uD83C\uDF27\uFE0F";
      case "high_wind": return "\uD83D\uDCA8";
      case "flooding": return "\uD83C\uDF0A";
      case "storm_surge": return "\uD83C\uDF0A";
      case "low_visibility": return "\uD83C\uDF2B\uFE0F";
      case "pressure": return "\uD83D\uDD3B";
      case "tornado": return "\uD83C\uDF2A\uFE0F";
      default: return "\u2601\uFE0F";
    }
  };

  const weatherSeverityColor = (severity: string): { bg: string; text: string; dot: string } => {
    switch (severity) {
      case "extreme":
        return {
          bg: isDark ? "bg-red-900/60" : "bg-red-100",
          text: isDark ? "text-red-300" : "text-red-700",
          dot: "bg-red-500",
        };
      case "high":
        return {
          bg: isDark ? "bg-orange-900/60" : "bg-orange-100",
          text: isDark ? "text-orange-300" : "text-orange-700",
          dot: "bg-orange-500",
        };
      case "medium":
        return {
          bg: isDark ? "bg-amber-900/60" : "bg-amber-100",
          text: isDark ? "text-amber-300" : "text-amber-700",
          dot: "bg-amber-500",
        };
      default:
        return {
          bg: isDark ? "bg-sky-900/60" : "bg-sky-100",
          text: isDark ? "text-sky-300" : "text-sky-700",
          dot: "bg-sky-500",
        };
    }
  };

  const conditionLabel = (conditionType?: WeatherConditionType): string => {
    switch (conditionType) {
      case "cyclone": return "Cyclone";
      case "thunderstorm": return "Thunderstorm";
      case "heavy_rain": return "Rainfall";
      case "high_wind": return "Wind";
      case "flooding": return "Flood Risk";
      case "storm_surge": return "Storm Surge";
      case "low_visibility": return "Visibility";
      case "pressure": return "Pressure";
      case "tornado": return "Tornado";
      default: return "Weather";
    }
  };

  const renderWeather = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => (
        <View key={`weather-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
          <Text
            className={`text-xs font-semibold uppercase ${getFreshnessColor(step.sectionUpdatedAt.weather)}`}
          >
            Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.weather)}
          </Text>
          {step.weather.map((item) => {
            const sevColors = weatherSeverityColor(item.severity);
            return (
              <View
                key={`weather-step-${stepIndex}-${item.id}`}
                className={`mt-3 rounded-xl border p-4 ${
                  isDark
                    ? "border-brand-darkBorder bg-brand-darkSurface"
                    : "border-brand-border bg-brand-surface"
                }`}
              >
                <View className="flex-row items-start">
                  <View
                    className={`mr-3 h-10 w-10 items-center justify-center rounded-lg ${
                      isDark ? "bg-slate-700" : "bg-slate-200"
                    }`}
                  >
                    <Text className="text-lg">{weatherGlyph(item.conditionType)}</Text>
                  </View>
                  <View className="flex-1">
                    <View className="flex-row items-center justify-between">
                      <Text
                        className={`flex-1 text-base font-semibold ${
                          isDark ? "text-brand-darkInk" : "text-brand-ink"
                        }`}
                        numberOfLines={2}
                      >
                        {item.headline}
                      </Text>
                    </View>
                    <View className="mt-1.5 flex-row items-center">
                      <View className={`rounded-md px-2 py-0.5 ${sevColors.bg}`}>
                        <View className="flex-row items-center">
                          <View className={`mr-1.5 h-1.5 w-1.5 rounded-full ${sevColors.dot}`} />
                          <Text className={`text-[11px] font-semibold uppercase ${sevColors.text}`}>
                            {item.severity}
                          </Text>
                        </View>
                      </View>
                      {item.conditionType && item.conditionType !== "general" ? (
                        <View
                          className={`ml-2 rounded-md px-2 py-0.5 ${
                            isDark ? "bg-slate-700" : "bg-slate-200"
                          }`}
                        >
                          <Text
                            className={`text-[11px] font-medium ${
                              isDark ? "text-slate-300" : "text-slate-600"
                            }`}
                          >
                            {conditionLabel(item.conditionType)}
                          </Text>
                        </View>
                      ) : null}
                    </View>
                  </View>
                </View>

                <Text
                  className={`mt-3 text-sm leading-6 ${
                    isDark ? "text-brand-darkInk" : "text-brand-ink"
                  }`}
                >
                  {item.details}
                </Text>

                <Text className={`mt-2 text-[10px] ${getFreshnessColor(item.updatedAt)}`}>
                  Updated: {formatTime(item.updatedAt)}
                </Text>
              </View>
            );
          })}
          {stepIndex !== currentStepIndex ? (
            <View
              pointerEvents="none"
              className="absolute inset-0 rounded-2xl"
              style={{ backgroundColor: isDark ? "rgba(100,116,139,0.34)" : "rgba(148,163,184,0.28)" }}
            />
          ) : null}
        </View>
      ))}
    </View>
  );

  return (
    <>
      <FlatList
        className={`flex-1 ${isDark ? "bg-brand-darkSurface" : "bg-brand-surface"}`}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 14, paddingBottom: 18 }}
        data={[section]}
        keyExtractor={(item) => item}
        renderItem={() => {
          if (section === "alerts") {
            return renderAlerts();
          }

          if (section === "evacuation plans") {
            return renderPlans();
          }

          if (section === "my connections") {
            return renderConnections();
          }

          if (section === "saved information") {
            return renderSavedInformation();
          }

          return renderWeather();
        }}
        ListHeaderComponent={
          <View className="mb-3">
            <View className="flex-row items-center">
              <Pressable
                className={`relative h-10 w-10 items-center justify-center rounded-xl border ${
                  isDark ? "border-slate-700 bg-slate-900" : "border-brand-border bg-brand-card shadow-soft"
                }`}
                onPress={() => {
                  setMenuOpen(true);
                }}
              >
                <Text className={`text-xl ${isDark ? "text-slate-100" : "text-slate-900"}`}>&#9776;</Text>
                {unreadUpdates > 0 ? (
                  <View className="absolute -right-3 -top-2 rounded-full bg-red-600 px-2 py-0.5">
            <Text className="text-[10px] font-semibold text-white">{unreadUpdates > 99 ? "99+" : unreadUpdates} </Text>
          </View>
        ) : null}
              </Pressable>

              <Text className={`ml-3 text-2xl font-semibold ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}>
                {toSectionTitle(section)}
              </Text>

              <View style={{ flex: 1 }} />

              <Image source={logoGreenBlue} style={{ width: 40, height: 40, resizeMode: "contain", marginRight: 6 }} />
              <VoiceWidget/>
            </View>

            <Text className={`mt-2 text-xs ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
              Step {currentStepIndex + 1}/{totalSteps} | T+{currentStepIndex * DISASTER_STEP_INTERVAL_MINUTES}m
            </Text>
            <Text className={`mt-1 text-xs ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
              {toSectionTitle(section)} updated:{" "}
              <Text className={getFreshnessColor(latestStep.sectionUpdatedAt[toSectionUpdatedAtKey(section)])}>
                {formatTime(latestStep.sectionUpdatedAt[toSectionUpdatedAtKey(section)])}
              </Text>
            </Text>
          </View>
        }
      />

      <Modal transparent visible={menuOpen} animationType="fade" onRequestClose={() => setMenuOpen(false)}>
        <Pressable className="flex-1 bg-black/20" onPress={() => setMenuOpen(false)}>
          <View
            className={`ml-4 mt-20 w-56 rounded-2xl border p-2 ${
              isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
            }`}
          >
            {SECTION_OPTIONS.map((option) => {
              const selected = section === option;
              const optionKey = toSectionUpdatedAtKey(option);
              const unreadCount = unreadBySection[optionKey];

              return (
                <Pressable
                  key={option}
                  className={`mb-1 rounded-xl px-3 py-2 ${
                    selected ? (isDark ? "bg-slate-700" : "bg-slate-200") : "bg-transparent"
                  }`}
                  onPress={() => {
                    setSection(option);
                    markSectionSeen(optionKey);
                    setMenuOpen(false);
                  }}
                >
                  <View className="flex-row items-center justify-between">
                    <Text className={`text-sm font-semibold capitalize ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                      {option}
                    </Text>
                    {unreadCount > 0 ? (
                      <View className="rounded-full bg-red-600 px-2 py-0.5">
                        <Text className="text-[10px] font-semibold text-white">{unreadCount}</Text>
                      </View>
                    ) : null}
                  </View>
                </Pressable>
              );
            })}
          </View>
        </Pressable>
      </Modal>
    </>
  );
}
