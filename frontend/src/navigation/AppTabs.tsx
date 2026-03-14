import { useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { userProfileMock } from "../data";
import { InfoScreen } from "../screens/InfoScreen";
import { MapScreen } from "../screens/MapScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { AppTheme } from "../types/theme";

type TabKey = "info" | "map" | "profile";
type TabIconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

const TAB_OPTIONS: { key: TabKey; label: string; icon: TabIconName }[] = [
  { key: "info", label: "Info", icon: "information-outline" },
  { key: "map", label: "Map", icon: "map-marker-radius-outline" },
  { key: "profile", label: "Profile", icon: "account-circle-outline" }
];

export function AppTabs() {
  const [activeTab, setActiveTab] = useState<TabKey>("info");
  const [theme, setTheme] = useState<AppTheme>("light");
  const [fullName, setFullName] = useState(userProfileMock.fullName);
  const [phoneNumber, setPhoneNumber] = useState(userProfileMock.phoneNumber);
  const [homeArea, setHomeArea] = useState(userProfileMock.homeArea);

  const insets = useSafeAreaInsets();
  const isDark = theme === "dark";

  const activeScreen = useMemo(() => {
    switch (activeTab) {
      case "map":
        return <MapScreen theme={theme} />;
      case "profile":
        return (
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
        );
      case "info":
      default:
        return <InfoScreen theme={theme} userPhoneNumber={phoneNumber} />;
    }
  }, [activeTab, fullName, homeArea, phoneNumber, theme]);

  return (
    <View className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      <View className="flex-1">{activeScreen}</View>

      <View
        className={`border-t px-3 ${
          isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
        }`}
        style={{ paddingBottom: Math.max(insets.bottom, 6), paddingTop: 6 }}
      >
        <View className="flex-row items-center justify-between">
          {TAB_OPTIONS.map((tab) => {
            const isActive = activeTab === tab.key;
            const iconColor = isActive
              ? isDark
                ? "#0f172a"
                : "#f8fafc"
              : isDark
                ? "#cbd5e1"
                : "#334155";

            return (
              <Pressable
                key={tab.key}
                className={`mx-1 flex-1 items-center rounded-xl px-1 py-1.5 ${
                  isActive
                    ? isDark
                      ? "bg-slate-100"
                      : "bg-slate-900"
                    : isDark
                      ? "bg-slate-800"
                      : "bg-slate-200"
                }`}
                onPress={() => setActiveTab(tab.key)}
              >
                <MaterialCommunityIcons name={tab.icon} size={18} color={iconColor} />
                <Text
                  className={`mt-0.5 text-[10px] font-semibold ${
                    isActive
                      ? isDark
                        ? "text-slate-900"
                        : "text-slate-100"
                      : isDark
                        ? "text-slate-300"
                        : "text-slate-700"
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
