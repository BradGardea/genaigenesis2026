import { useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { userProfileMock } from "../data";
import { InfoScreen } from "../screens/InfoScreen";
import { MapScreen } from "../screens/MapScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { useDisasterDemo } from "../state/DisasterDemoContext";
import { AppTheme } from "../types/theme";

type TabKey = "info" | "map" | "profile";
type TabIconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

const TAB_OPTIONS: { key: TabKey; label: string; icon: TabIconName }[] = [
  { key: "info", label: "Info", icon: "information-outline" },
  { key: "map", label: "Map", icon: "map-marker-radius-outline" },
  { key: "profile", label: "Profile", icon: "account-circle-outline" },
];

export function AppTabs() {
  const [activeTab, setActiveTab] = useState<TabKey>("info");
  const [theme, setTheme] = useState<AppTheme>("dark");
  const [fullName, setFullName] = useState(userProfileMock.fullName);
  const [phoneNumber, setPhoneNumber] = useState(userProfileMock.phoneNumber);
  const [homeArea, setHomeArea] = useState(userProfileMock.homeArea);
  const {
    currentStepIndex,
    totalSteps,
    isFinalStep,
    isStepping,
    stepDisaster,
    latestHighRiskAlert,
  } = useDisasterDemo();
  const [isPlaying, setIsPlaying] = useState(false);
  const [visibleAlertBanner, setVisibleAlertBanner] = useState<{
    id: string;
    title: string;
    urgency: string;
    stepLabel: string;
  } | null>(null);

  const insets = useSafeAreaInsets();
  const isDark = theme === "dark";

  useEffect(() => {
    if (!isPlaying) return;
    if (isFinalStep) {
      setIsPlaying(false);
      return;
    }
    if (isStepping) return;
    const timer = setTimeout(() => {
      void stepDisaster({ beautify: activeTab !== "map" });
    }, 500);
    return () => clearTimeout(timer);
  }, [
    isPlaying,
    isFinalStep,
    isStepping,
    currentStepIndex,
    activeTab,
    stepDisaster,
  ]);

  useEffect(() => {
    if (!latestHighRiskAlert) {
      return;
    }

    setVisibleAlertBanner({
      id: `${latestHighRiskAlert.stepIndex}-${latestHighRiskAlert.title}`,
      title: latestHighRiskAlert.title,
      urgency: latestHighRiskAlert.urgency,
      stepLabel: `Step ${latestHighRiskAlert.stepIndex + 1}`,
    });

    const timeout = setTimeout(() => {
      setVisibleAlertBanner(null);
    }, 3500);

    return () => {
      clearTimeout(timeout);
    };
  }, [latestHighRiskAlert]);

  return (
    <View className={`flex-1 ${isDark ? "bg-brand-darkSurface" : "bg-brand-surface"}`}>
      {visibleAlertBanner ? (
        <View
          className={`absolute left-3 right-3 top-10 z-20 rounded-xl border px-3 py-2 ${
            isDark ? "border-red-400 bg-red-900" : "border-red-300 bg-red-50"
          }`}
        >
          <Text
            className={`text-[11px] font-semibold uppercase ${isDark ? "text-red-100" : "text-red-700"}`}
          >
            High risk update | {visibleAlertBanner.urgency} |{" "}
            {visibleAlertBanner.stepLabel}
          </Text>
          <Text
            className={`mt-1 text-xs font-medium ${isDark ? "text-red-100" : "text-red-800"}`}
          >
            {visibleAlertBanner.title}
          </Text>
        </View>
      ) : null}

      <View className="flex-1">
        <View
          style={{ display: activeTab === "info" ? "flex" : "none", flex: 1 }}
        >
          <InfoScreen theme={theme} />
        </View>
        <View
          style={{ display: activeTab === "map" ? "flex" : "none", flex: 1 }}
        >
          <MapScreen theme={theme} />
        </View>
        <View
          style={{
            display: activeTab === "profile" ? "flex" : "none",
            flex: 1,
          }}
        >
          <ProfileScreen
            theme={theme}
            onThemeChange={setTheme}
            fullName={fullName}
            onFullNameChange={setFullName}
            phoneNumber={phoneNumber}
            onPhoneNumberChange={setPhoneNumber}
            homeArea={homeArea}
            onHomeAreaChange={setHomeArea}
          />
        </View>
      </View>
      <View
        className="absolute left-4 flex-row gap-2"
        style={{ bottom: Math.max(insets.bottom, 6) + 64 }}
      >
        <Pressable
          className={`rounded-xl border px-4 py-2 ${
            isFinalStep
              ? isDark
                ? "border-slate-700 bg-slate-800"
                : "border-slate-300 bg-slate-200"
              : isDark
                ? "border-rose-700 bg-rose-900"
                : "border-rose-300 bg-rose-50"
          }`}
          disabled={isFinalStep}
          onPress={() => setIsPlaying((p) => !p)}
        >
          <Text
            className={`text-xs font-semibold select-none ${
              isFinalStep
                ? isDark
                  ? "text-slate-300"
                  : "text-slate-600"
                : isDark
                  ? "text-rose-100"
                  : "text-rose-700"
            }`}
          >
            {isFinalStep ? "Done" : isPlaying ? "⏸ Pause" : "▶ Play"}
          </Text>
        </Pressable>
        <Pressable
          className={`rounded-xl border px-4 py-2 ${
            isFinalStep || isStepping || isPlaying
              ? isDark
                ? "border-slate-700 bg-slate-800"
                : "border-slate-300 bg-slate-200"
              : isDark
                ? "border-rose-700 bg-rose-900"
                : "border-rose-300 bg-rose-50"
          }`}
          disabled={isFinalStep || isStepping || isPlaying}
          onPress={() => {
            void stepDisaster({ beautify: activeTab !== "map" });
          }}
        >
          <Text
            className={`text-xs font-semibold select-none ${
              isFinalStep || isStepping || isPlaying
                ? isDark
                  ? "text-slate-300"
                  : "text-slate-600"
                : isDark
                  ? "text-rose-100"
                  : "text-rose-700"
            }`}
          >
            {isStepping
              ? "..."
              : `→ Step (${Math.min(currentStepIndex + 1, totalSteps)}/${totalSteps})`}
          </Text>
        </Pressable>
      </View>

      <View
        className={`border-t px-3 ${
          isDark ? "border-brand-darkBorder bg-brand-darkCard" : "border-brand-border bg-brand-card"
        }`}
        style={{ paddingBottom: Math.max(insets.bottom, 6), paddingTop: 6 }}
      >
        <View className="flex-row items-center justify-between">
          {TAB_OPTIONS.map((tab) => {
            const isActive = activeTab === tab.key;
            const iconColor = isActive
              ? isDark
                ? "#e5e7eb"
                : "#f8fafc"
              : isDark
                ? "#cbd5e1"
                : "#1f4b99";

            return (
              <Pressable
                key={tab.key}
                className={`mx-1 flex-1 items-center rounded-xl px-1 py-1.5 ${
                  isActive
                    ? isDark
                      ? "bg-brand-darkMuted/20"
                      : "bg-brand-primary"
                    : isDark
                      ? "bg-brand-darkCard"
                      : "bg-brand-card"
                }`}
                onPress={() => setActiveTab(tab.key)}
              >
                <MaterialCommunityIcons
                  name={tab.icon}
                  size={18}
                  color={iconColor}
                />
                <Text
                  className={`mt-0.5 text-[10px] font-semibold ${
                    isActive
                      ? isDark
                        ? "text-brand-darkInk"
                        : "text-white"
                      : isDark
                        ? "text-brand-darkMuted"
                        : "text-brand-ink"
                  }`}
                >
                  {tab.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}
