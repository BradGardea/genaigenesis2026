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
  return (
    <ScrollView className="flex-1 bg-crisis-bg px-4 pt-12">
      <Text className="mb-1 text-3xl font-bold text-crisis-text">CrisisNet</Text>
      <Text className="mb-6 text-sm text-crisis-muted">
        Early warning, live detection, and personalized evacuation planning.
      </Text>

      <StatusCard
        title="Early Warning"
        description="Risk signals aggregated from weather and seismic pipelines."
        badgeLabel="Monitoring"
        badgeColorClass="bg-crisis-warn"
      >
        {riskSignals.map((signal) => (
          <View key={signal.id} className="mb-2 rounded-xl bg-black/20 p-3">
            <Text className="text-sm font-semibold text-crisis-text">{signal.name}</Text>
            <Text className="text-xs text-crisis-muted">
              {signal.value} | {signal.source}
            </Text>
          </View>
        ))}
      </StatusCard>

      <StatusCard
        title="Detection"
        description="Incoming incidents correlated across dispatch, weather, and social channels."
        badgeLabel="1 Active"
        badgeColorClass="bg-crisis-danger"
      >
        {recentEvents.map((event) => (
          <View key={event.id} className="mb-2 rounded-xl bg-black/20 p-3">
            <Text className="text-sm font-semibold text-crisis-text">{event.title}</Text>
            <Text className="text-xs text-crisis-muted">
              {event.location} | {event.source}
            </Text>
          </View>
        ))}
      </StatusCard>

      <StatusCard
        title="Response"
        description="Personalized profile used to build evacuation protocol and route guidance."
        badgeLabel="Profile Ready"
        badgeColorClass="bg-crisis-ok"
      >
        <Text className="mb-3 text-xs text-crisis-muted">
          Family: {sampleProfile.familySize} | Vehicles: {sampleProfile.vehicles} | Children:{" "}
          {sampleProfile.hasChildren ? "Yes" : "No"}
        </Text>
        <Pressable className="rounded-xl bg-crisis-text p-3">
          <Text className="text-center font-semibold text-crisis-bg">
            Build Evacuation Plan
          </Text>
        </Pressable>
      </StatusCard>
    </ScrollView>
  );
}

