import { Pressable, ScrollView, Text, View } from "react-native";
import { StatusCard } from "../components/StatusCard";
import { EmergencyEvent, EvacuationProfile, RiskSignal } from "../types/domain";
import VoiceWidget from "@/components/Audio";

const riskSignals: RiskSignal[] = [
  {
    id: "sig-1",
    name: "Drought Index",
    value: "Very Dry",
    severity: "high",
    source: "Weather API"
  },
  {
    id: "sig-2",
    name: "Seismic Activity",
    value: "Elevated micro-tremors",
    severity: "medium",
    source: "Geo Feed"
  }
];

const recentEvents: EmergencyEvent[] = [
  {
    id: "evt-1",
    title: "Wildfire reported",
    location: "North Ridge",
    severity: "high",
    detectedAt: "2026-03-09T21:40:00Z",
    source: "Dispatch Audio + Social"
  }
];

const sampleProfile: EvacuationProfile = {
  familySize: 4,
  vehicles: 1,
  hasChildren: true,
  hasElderly: false,
  hasMobilityNeeds: false
};

export function HomeScreen() {
  const isDark = false;
  return (
    <ScrollView className="flex-1 bg-brand-surface px-4 pt-12">
      <Text className="mb-1 text-3xl font-bold text-brand-ink">CrisisNet</Text>
      <Text className="mb-6 text-sm text-brand-muted">
        Early warning, live detection, and personalized evacuation planning.
      </Text>

      <StatusCard
        title="Early Warning"
        description="Risk signals aggregated from weather and seismic pipelines."
        badgeLabel="Monitoring"
        badgeColorClass="bg-status-warn text-brand-ink"
        isDark={isDark}
      >
        {riskSignals.map((signal) => (
          <View key={signal.id} className="mb-2 rounded-xl bg-brand-card p-3 shadow-soft">
            <Text className="text-sm font-semibold text-brand-ink">{signal.name}</Text>
            <Text className="text-xs text-brand-muted">
              {signal.value} | {signal.source}
            </Text>
          </View>
        ))}
      </StatusCard>

      <StatusCard
        title="Detection"
        description="Incoming incidents correlated across dispatch, weather, and social channels."
        badgeLabel="1 Active"
        badgeColorClass="bg-status-danger text-white"
        isDark={isDark}
      >
        {recentEvents.map((event) => (
          <View key={event.id} className="mb-2 rounded-xl bg-brand-card p-3 shadow-soft">
            <Text className="text-sm font-semibold text-brand-ink">{event.title}</Text>
            <Text className="text-xs text-brand-muted">
              {event.location} | {event.source}
            </Text>
          </View>
        ))}
      </StatusCard>

      <StatusCard
        title="Response"
        description="Personalized profile used to build evacuation protocol and route guidance."
        badgeLabel="Profile Ready"
        badgeColorClass="bg-status-success text-brand-ink"
        isDark={isDark}
      >
        <Text className="mb-3 text-xs text-brand-muted">
          Family: {sampleProfile.familySize} | Vehicles: {sampleProfile.vehicles} | Children:{" "}
          {sampleProfile.hasChildren ? "Yes" : "No"}
        </Text>
        <Pressable className="rounded-xl bg-brand-primary p-3 shadow-soft">
          <Text className="text-center font-semibold text-white">
            Build Evacuation Plan
          </Text>
        </Pressable>
      </StatusCard>
    </ScrollView>
  );
}

