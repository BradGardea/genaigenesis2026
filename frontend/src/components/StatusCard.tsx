import { ReactNode } from "react";
import { Text, View } from "react-native";

interface StatusCardProps {
  title: string;
  description: string;
  badgeLabel: string;
  badgeColorClass: string;
  children?: ReactNode;
}

export function StatusCard({
  title,
  description,
  badgeLabel,
  badgeColorClass,
  children
}: StatusCardProps) {
  return (
    <View className="mb-4 rounded-xl border border-brand-border bg-brand-card p-4 shadow-soft">
      <View className="mb-3 flex-row items-center justify-between">
        <Text className="text-lg font-semibold text-brand-ink">{title}</Text>
        <View className={`rounded-pill px-3 py-1 ${badgeColorClass}`}>
          <Text className="text-xs font-semibold text-brand-ink">{badgeLabel}</Text>
        </View>
      </View>
      <Text className="mb-3 text-sm text-brand-muted">{description}</Text>
      {children}
    </View>
  );
}

