import { Text, View } from "react-native";
import { mapIncidentPointsMock } from "../data";
import { AppTheme } from "../types/theme";

interface MapScreenProps {
  theme: AppTheme;
}

export function MapScreen({ theme }: MapScreenProps) {
  const isDark = theme === "dark";

  return (
    <View className={`flex-1 px-4 pt-3 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      <Text className={`text-sm ${isDark ? "text-slate-400" : "text-slate-600"}`}>
        Web Mapbox is enabled. Native map is currently disabled in this setup.
      </Text>

      <View
        className={`mt-3 flex-1 items-center justify-center rounded-2xl border border-dashed px-4 ${
          isDark ? "border-slate-600 bg-slate-800" : "border-slate-300 bg-slate-50"
        }`}
      >
        <Text className={`text-center text-sm ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          Native fallback screen. Seeded points: {mapIncidentPointsMock.length}
        </Text>
      </View>
    </View>
  );
}
