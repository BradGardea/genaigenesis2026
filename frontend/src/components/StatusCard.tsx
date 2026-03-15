import { ReactNode } from "react";
import { Text, View } from "react-native";

interface StatusCardProps {
  title: string;
  description: string;
  badgeLabel: string;
  badgeColorClass: string;
  children?: ReactNode;
  isDark?: boolean;
}

export function StatusCard({
  title,
  description,
  badgeLabel,
  badgeColorClass,
  children,
  isDark = false
}: StatusCardProps) {
  return (
    <View
      className={`mb-4 rounded-xl border p-4 shadow-soft ${
        isDark ? "border-brand-darkBorder bg-brand-darkCard" : "border-brand-border bg-brand-card"
      }`}
    >
      <View className="mb-3 flex-row items-center justify-between">
        <Text className={`text-lg font-semibold ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}>{title}</Text>
        <View className={`rounded-pill px-3 py-1 ${badgeColorClass}`}>
          <Text className={`text-xs font-semibold ${isDark ? "text-brand-darkInk" : "text-brand-ink"}`}>{badgeLabel}</Text>
        </View>
      </View>
      <Text className={`mb-3 text-sm ${isDark ? "text-brand-darkMuted" : "text-brand-muted"}`}>{description}</Text>
      {children}
    </View>
  );
}

