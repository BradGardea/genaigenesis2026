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
  PersonSummary
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
                      <Text className={`text-xs font-semibold ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
                        {item.category}
                      </Text>
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
                      <Text className={`text-xs ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
                        Area: {item.area}
                      </Text>
                      <Text className={`mt-1 text-xs ${getFreshnessColor(item.occurredAt)}`}>
                        Occurred: {formatTime(item.occurredAt)}
                      </Text>
                      <Text className={`mt-1 text-xs ${getFreshnessColor(item.updatedAt)}`}>
                        Updated: {formatTime(item.updatedAt)}
                      </Text>
                      <Text className={`mt-1 text-xs ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>
                        Source: {item.source}
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

  const renderSavedInformation = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => (
        <View key={`saved-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
          <Text
            className={`text-xs font-semibold uppercase ${getFreshnessColor(step.sectionUpdatedAt.savedInformation)}`}
          >
            Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.savedInformation)}
          </Text>
          {step.savedInformation.map((item) => (
            <View key={`saved-step-${stepIndex}-${item.id}`} className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
              <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                {item.title}
              </Text>
              <Text className={`mt-2 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.note}</Text>
              <Text className={`mt-2 text-xs ${getFreshnessColor(item.updatedAt)}`}>
                Updated: {formatTime(item.updatedAt)}
              </Text>
            </View>
          ))}
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

  const renderWeather = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => (
        <View key={`weather-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
          <Text
            className={`text-xs font-semibold uppercase ${getFreshnessColor(step.sectionUpdatedAt.weather)}`}
          >
            Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.weather)}
          </Text>
          {step.weather.map((item) => (
            <View key={`weather-step-${stepIndex}-${item.id}`} className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
              <View className="flex-row items-center justify-between">
                <Text className={`mr-2 flex-1 text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                  {item.headline}
                </Text>
                <Text className={`text-xs font-semibold uppercase ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                  {item.severity}
                </Text>
              </View>
              <Text className={`mt-2 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.details}</Text>
              <Text className={`mt-2 text-xs ${getFreshnessColor(item.updatedAt)}`}>
                Updated: {formatTime(item.updatedAt)}
              </Text>
            </View>
          ))}
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
            <Text className="text-[10px] font-semibold text-white">{unreadUpdates} new</Text>
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
