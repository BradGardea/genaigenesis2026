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
    <View className="mb-4 rounded-2xl bg-crisis-panel p-4">
      <View className="mb-3 flex-row items-center justify-between">
        <Text className="text-lg font-semibold text-crisis-text">{title}</Text>
        <View className={`rounded-full px-3 py-1 ${badgeColorClass}`}>
          <Text className="text-xs font-semibold text-black">{badgeLabel}</Text>
        </View>
      </View>
      <Text className="mb-3 text-sm text-crisis-muted">{description}</Text>
      {children}
    </View>
  );
}

