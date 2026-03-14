import { useEffect, useMemo, useState } from "react";
import { FlatList, Modal, Pressable, Text, View } from "react-native";
import {
  EvacuationPlan,
  fetchConnections,
  fetchEvacuationPlans,
  fetchInfoAlerts,
  fetchSavedInformation,
  fetchWeatherUpdates,
  InfoBubble,
  SavedInformation,
  URGENCY_CARD_COLORS,
  URGENCY_WEIGHT,
  UserConnection,
  WeatherUpdate
} from "../data";
import { AppTheme } from "../types/theme";

type InfoSection =
  | "alerts"
  | "evacuation plans"
  | "my connections"
  | "saved information"
  | "weather";

interface InfoScreenProps {
  theme: AppTheme;
  userPhoneNumber: string;
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

export function InfoScreen({ theme, userPhoneNumber }: InfoScreenProps) {
  const isDark = theme === "dark";
  const [menuOpen, setMenuOpen] = useState(false);
  const [section, setSection] = useState<InfoSection>("alerts");

  const [alerts, setAlerts] = useState<InfoBubble[]>([]);
  const [plans, setPlans] = useState<EvacuationPlan[]>([]);
  const [connections, setConnections] = useState<UserConnection[]>([]);
  const [savedItems, setSavedItems] = useState<SavedInformation[]>([]);
  const [weather, setWeather] = useState<WeatherUpdate[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const sortedAlerts = useMemo(
    () =>
      [...alerts].sort((left, right) => {
        const urgencyDiff = URGENCY_WEIGHT[right.urgency] - URGENCY_WEIGHT[left.urgency];

        if (urgencyDiff !== 0) {
          return urgencyDiff;
        }

        return new Date(right.occurredAt).getTime() - new Date(left.occurredAt).getTime();
      }),
    [alerts]
  );

  const sortedPlans = useMemo(
    () => [...plans].sort((left, right) => right.successProbability - left.successProbability),
    [plans]
  );

  useEffect(() => {
    let cancelled = false;

    async function loadBaseData() {
      setLoading(true);
      setErrorMessage(null);

      try {
        const [nextAlerts, nextPlans, nextSaved, nextWeather] = await Promise.all([
          fetchInfoAlerts(),
          fetchEvacuationPlans(),
          fetchSavedInformation(),
          fetchWeatherUpdates()
        ]);

        if (cancelled) {
          return;
        }

        setAlerts(nextAlerts);
        setPlans(nextPlans);
        setSavedItems(nextSaved);
        setWeather(nextWeather);
      } catch {
        if (!cancelled) {
          setErrorMessage("Unable to load information from backend.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadBaseData();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadConnections() {
      try {
        const nextConnections = await fetchConnections(userPhoneNumber);

        if (!cancelled) {
          setConnections(nextConnections);
        }
      } catch {
        if (!cancelled) {
          setErrorMessage("Unable to load connection updates.");
        }
      }
    }

    if (userPhoneNumber.trim().length > 0) {
      void loadConnections();
    }

    return () => {
      cancelled = true;
    };
  }, [userPhoneNumber]);

  const commonCardClass = `mb-3 rounded-2xl border p-4 ${
    isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
  }`;

  const renderAlerts = () => (
    <FlatList
      data={sortedAlerts}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => {
        const colorSet = URGENCY_CARD_COLORS[item.urgency][theme];

        return (
          <View
            className="mb-3 rounded-2xl border p-4"
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
              <Text className={`mt-1 text-xs ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                Occurred: {formatTime(item.occurredAt)}
              </Text>
              <Text className={`mt-1 text-xs ${isDark ? "text-slate-200" : "text-slate-700"}`}>
                Source: {item.source}
              </Text>
            </View>
          </View>
        );
      }}
      scrollEnabled={false}
    />
  );

  const renderPlans = () => (
    <FlatList
      data={sortedPlans}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <View className={commonCardClass}>
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

          <Text className={`mb-3 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>
            {item.summary}
          </Text>

          <Text className={`mb-1 text-xs font-semibold uppercase ${isDark ? "text-slate-400" : "text-slate-600"}`}>
            Steps
          </Text>
          {item.steps.map((step, index) => (
            <Text
              key={`${item.id}-step-${index + 1}`}
              className={`mb-1 text-sm ${isDark ? "text-slate-200" : "text-slate-800"}`}
            >
              {index + 1}. {step}
            </Text>
          ))}

          <Text
            className={`mb-1 mt-3 text-xs font-semibold uppercase ${
              isDark ? "text-slate-400" : "text-slate-600"
            }`}
          >
            Pack if possible
          </Text>
          {item.packingList.map((entry, index) => (
            <Text
              key={`${item.id}-pack-${index + 1}`}
              className={`mb-1 text-sm ${isDark ? "text-slate-200" : "text-slate-800"}`}
            >
              - {entry}
            </Text>
          ))}
        </View>
      )}
      scrollEnabled={false}
    />
  );

  const renderConnections = () => (
    <FlatList
      data={connections}
      keyExtractor={(item) => item.id}
      ListEmptyComponent={
        <View className={commonCardClass}>
          <Text className={`${isDark ? "text-slate-300" : "text-slate-700"}`}>
            No connections yet. Add one from Profile.
          </Text>
        </View>
      }
      renderItem={({ item }) => (
        <View className={commonCardClass}>
          <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
            {item.contactPhone}
          </Text>
          <Text className={`mt-1 text-sm capitalize ${isDark ? "text-slate-300" : "text-slate-700"}`}>
            Relationship: {item.relationship}
          </Text>
          <Text className={`mt-1 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>
            Trust level: {item.trustLevel}
          </Text>
          <Text className={`mt-1 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Updated: {formatTime(item.updatedAt)}
          </Text>
        </View>
      )}
      scrollEnabled={false}
    />
  );

  const renderSavedInformation = () => (
    <FlatList
      data={savedItems}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <View className={commonCardClass}>
          <Text className={`text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
            {item.title}
          </Text>
          <Text className={`mt-2 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.note}</Text>
          <Text className={`mt-2 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Updated: {formatTime(item.updatedAt)}
          </Text>
        </View>
      )}
      scrollEnabled={false}
    />
  );

  const renderWeather = () => (
    <FlatList
      data={weather}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <View className={commonCardClass}>
          <View className="flex-row items-center justify-between">
            <Text className={`mr-2 flex-1 text-base font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
              {item.headline}
            </Text>
            <Text className={`text-xs font-semibold uppercase ${isDark ? "text-slate-300" : "text-slate-700"}`}>
              {item.severity}
            </Text>
          </View>
          <Text className={`mt-2 text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>{item.details}</Text>
          <Text className={`mt-2 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Updated: {formatTime(item.updatedAt)}
          </Text>
        </View>
      )}
      scrollEnabled={false}
    />
  );

  return (
    <>
      <FlatList
        className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 14, paddingBottom: 18 }}
        data={[section]}
        keyExtractor={(item) => item}
        renderItem={() => {
          if (loading) {
            return (
              <Text className={`text-sm ${isDark ? "text-slate-300" : "text-slate-700"}`}>
                Loading information...
              </Text>
            );
          }

          if (errorMessage) {
            return <Text className="text-sm text-red-500">{errorMessage}</Text>;
          }

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
          <View className="mb-3 flex-row items-center">
            <Pressable
              className={`h-10 w-10 items-center justify-center rounded-xl border ${
                isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
              }`}
              onPress={() => setMenuOpen(true)}
            >
              <Text className={`text-xl ${isDark ? "text-slate-100" : "text-slate-900"}`}>&#9776;</Text>
            </Pressable>

            <Text className={`ml-3 text-2xl font-semibold ${isDark ? "text-slate-100" : "text-slate-900"}`}>
              {toSectionTitle(section)}
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

              return (
                <Pressable
                  key={option}
                  className={`mb-1 rounded-xl px-3 py-2 ${
                    selected ? (isDark ? "bg-slate-700" : "bg-slate-200") : "bg-transparent"
                  }`}
                  onPress={() => {
                    setSection(option);
                    setMenuOpen(false);
                  }}
                >
                  <Text className={`text-sm font-semibold capitalize ${isDark ? "text-slate-100" : "text-slate-900"}`}>
                    {option}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </Pressable>
      </Modal>
    </>
  );
}
