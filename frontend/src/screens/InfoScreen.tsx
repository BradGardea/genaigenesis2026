import { useMemo, useState } from "react";
import { FlatList, Modal, Pressable, Text, View } from "react-native";
import {
  DISASTER_STEP_INTERVAL_MINUTES,
  EvacuationPlan,
  InfoBubble,
  disasterStepsMock,
  URGENCY_CARD_COLORS,
  URGENCY_WEIGHT,
} from "../data";
import { useDisasterDemo } from "../state/DisasterDemoContext";
import { AppTheme } from "../types/theme";

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

function hexToRgb(hex: string): [number, number, number] {
  const parsed = hex.replace("#", "");
  const value = Number.parseInt(parsed, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function interpolateHex(startHex: string, endHex: string, ratio: number): string {
  const clamped = Math.max(0, Math.min(1, ratio));
  const [r1, g1, b1] = hexToRgb(startHex);
  const [r2, g2, b2] = hexToRgb(endHex);
  const r = Math.round(r1 + (r2 - r1) * clamped);
  const g = Math.round(g1 + (g2 - g1) * clamped);
  const b = Math.round(b1 + (b2 - b1) * clamped);
  return `rgb(${r}, ${g}, ${b})`;
}

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
  const stepHistoryNewestFirst = useMemo(
    () => [...stepHistory].filter(({ stepIndex }) => stepIndex >= 0).reverse(),
    [stepHistory],
  );
  const latestStep = stepHistory[stepHistory.length - 1]?.step ?? disasterStepsMock[0];
  const referenceNowMs = new Date(latestStep.simulatedAt).getTime();

  const commonCardClass = `mb-3 rounded-2xl border p-4 ${
    isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
  }`;

  const getFreshnessColor = (isoTime: string): string => {
    const ageMinutes = Math.max(0, (referenceNowMs - new Date(isoTime).getTime()) / 60000);
    const green = "#16a34a";
    const yellow = "#eab308";
    const red = "#dc2626";

    if (ageMinutes <= 5) {
      return green;
    }

    if (ageMinutes <= 10) {
      return interpolateHex(green, yellow, (ageMinutes - 5) / 5);
    }

    if (ageMinutes <= 15) {
      return interpolateHex(yellow, red, (ageMinutes - 10) / 5);
    }

    return red;
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
              className="text-xs font-semibold uppercase"
              style={{ color: getFreshnessColor(step.sectionUpdatedAt.alerts) }}
            >
              Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.alerts)}
            </Text>
            {sortedAlerts.map((item) => {
              const colorSet = URGENCY_CARD_COLORS[item.urgency][theme];

              return (
                <View
                  key={`alerts-step-${stepIndex}-${item.id}`}
                  className="mb-3 mt-3 rounded-2xl border p-4"
                  style={{ backgroundColor: colorSet.backgroundColor, borderColor: colorSet.borderColor }}
                >
                  <View className="mb-2 self-start rounded-full border border-black/10 bg-white/55 px-3 py-1">
                    <Text
                      className="text-[11px] font-semibold uppercase"
                      style={{ color: URGENCY_PILL_TEXT_COLOR[item.urgency][theme] }}
                    >
                      {item.urgency}
                    </Text>
                  </View>
                  <Text className={`text-base font-semibold ${isDark ? "text-slate-50" : "text-slate-900"}`}>
                    {item.title}
                  </Text>
                  <Text
                    className={`mb-3 mt-1 text-xs uppercase tracking-wide ${
                      isDark ? "text-slate-200" : "text-slate-700"
                    }`}
                  >
                    {item.category}
                  </Text>
                  <Text className={`mb-3 text-sm ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                    {item.details}
                  </Text>
                  <View
                    className="rounded-xl p-3"
                    style={{ backgroundColor: isDark ? "rgba(15,23,42,0.35)" : "rgba(255,255,255,0.65)" }}
                  >
                    <Text className={`text-xs ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                      Area: {item.area}
                    </Text>
                    <Text className="mt-1 text-xs" style={{ color: getFreshnessColor(item.occurredAt) }}>
                      Occurred: {formatTime(item.occurredAt)}
                    </Text>
                    <Text className="mt-1 text-xs" style={{ color: getFreshnessColor(item.updatedAt) }}>
                      Updated: {formatTime(item.updatedAt)}
                    </Text>
                    <Text className={`mt-1 text-xs ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                      Source: {item.source}
                    </Text>
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
              className="text-xs font-semibold uppercase"
              style={{ color: getFreshnessColor(step.sectionUpdatedAt.evacuationPlans) }}
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
                  <Text className="mt-2 text-xs" style={{ color: getFreshnessColor(item.updatedAt) }}>
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

  const renderConnections = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => (
        <View key={`connections-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
          <Text
            className="text-xs font-semibold uppercase"
            style={{ color: getFreshnessColor(step.sectionUpdatedAt.connections) }}
          >
            Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.connections)}
          </Text>
          {step.connections.length === 0 ? (
            <Text className={`mt-3 ${isDark ? "text-slate-300" : "text-slate-700"}`}>No connections yet. Add one from Profile.</Text>
          ) : (
            step.connections.map((item) => (
              <View key={`connections-step-${stepIndex}-${item.id}`} className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
                <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                  {item.contactPhone}
                </Text>
                <Text className={`mt-1 text-sm capitalize ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                  Relationship: {item.relationship}
                </Text>
                <Text className={`mt-1 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                  Trust level: {item.trustLevel}
                </Text>
                <Text className="mt-1 text-xs" style={{ color: getFreshnessColor(item.updatedAt) }}>
                  Updated: {formatTime(item.updatedAt)}
                </Text>
              </View>
            ))
          )}
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

  const renderSavedInformation = () => (
    <View>
      {stepHistoryNewestFirst.map(({ step, stepIndex }) => (
        <View key={`saved-step-${stepIndex}`} className={`${commonCardClass} relative overflow-hidden`}>
          <Text
            className="text-xs font-semibold uppercase"
            style={{ color: getFreshnessColor(step.sectionUpdatedAt.savedInformation) }}
          >
            Step {stepIndex + 1} | fetched {formatTime(step.sectionUpdatedAt.savedInformation)}
          </Text>
          {step.savedInformation.map((item) => (
            <View key={`saved-step-${stepIndex}-${item.id}`} className={`mt-3 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-100"}`}>
              <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                {item.title}
              </Text>
              <Text className={`mt-2 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.note}</Text>
              <Text className="mt-2 text-xs" style={{ color: getFreshnessColor(item.updatedAt) }}>
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
            className="text-xs font-semibold uppercase"
            style={{ color: getFreshnessColor(step.sectionUpdatedAt.weather) }}
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
              <Text className="mt-2 text-xs" style={{ color: getFreshnessColor(item.updatedAt) }}>
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
        className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}
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
                  isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
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

              <Text className={`ml-3 text-2xl font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                {toSectionTitle(section)}
              </Text>
            </View>

            <Text className={`mt-2 text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
              Step {currentStepIndex + 1}/{totalSteps} | T+{currentStepIndex * DISASTER_STEP_INTERVAL_MINUTES}m
            </Text>
            <Text className={`mt-1 text-xs ${isDark ? "text-slate-400" : "text-slate-600"}`}>
              {toSectionTitle(section)} updated:{" "}
              <Text style={{ color: getFreshnessColor(latestStep.sectionUpdatedAt[toSectionUpdatedAtKey(section)]) }}>
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
