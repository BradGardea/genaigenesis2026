import { useEffect, useRef } from "react";
import { ScrollView, Text, View } from "react-native";
import type { AgentEvent } from "../services/simulationApi";
import type { AppTheme } from "../types/theme";

interface Props {
  theme: AppTheme;
  events: AgentEvent[];
}

const EVENT_CONFIG: Record<string, { color: string; icon: string }> = {
  depart: { color: "#60A5FA", icon: "\u2192" },
  reroute: { color: "#FBBF24", icon: "\u21BB" },
  shelter_in_place: { color: "#FB923C", icon: "\u2302" },
  arrived: { color: "#34D399", icon: "\u2713" },
};

function formatEvent(ev: AgentEvent): string {
  switch (ev.type) {
    case "depart":
      return `departed \u2192 ${ev.dest_name || "destination"}`;
    case "reroute":
      if (ev.dest_name) {
        return `rerouted \u2192 ${ev.dest_name}`;
      }
      return `rerouted \u2014 ${ev.reasoning || "hazard detected"}`;
    case "shelter_in_place":
      return "sheltering in place";
    case "arrived":
      return `arrived at ${ev.dest_name || "destination"}`;
    default:
      return ev.type;
  }
}

export function AgentActivityFeed({ theme, events }: Props) {
  const isDark = theme === "dark";
  const scrollRef = useRef<ScrollView>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    // Small delay so layout completes before scrolling
    const t = setTimeout(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    }, 50);
    return () => clearTimeout(t);
  }, [events.length]);

  const bg = isDark ? "#0F172A" : "#F8FAFC";
  const border = isDark ? "#1E293B" : "#E2E8F0";
  const textColor = isDark ? "#E2E8F0" : "#1E293B";
  const mutedColor = isDark ? "#64748B" : "#94A3B8";

  return (
    <View
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: bg,
        borderLeftWidth: 1,
        borderLeftColor: border,
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <View
        style={{
          paddingHorizontal: 14,
          paddingVertical: 10,
          borderBottomWidth: 1,
          borderBottomColor: border,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Text style={{ color: textColor, fontSize: 12, fontWeight: "700", letterSpacing: 0.5 }}>
          AGENT ACTIVITY
        </Text>
        <Text style={{ color: mutedColor, fontSize: 10 }}>
          {events.length} events
        </Text>
      </View>

      {/* Feed */}
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingVertical: 4 }}
        showsVerticalScrollIndicator
      >
        {events.length === 0 ? (
          <Text style={{ color: mutedColor, fontSize: 11, padding: 14, textAlign: "center" }}>
            Waiting for agent activity...
          </Text>
        ) : (
          // Events are stored newest-first; render oldest-first so scroll-to-bottom shows latest
          [...events].reverse().map((ev, i) => {
            const cfg = EVENT_CONFIG[ev.type] ?? EVENT_CONFIG.depart;
            return (
              <View
                key={`${ev.agent_id}-${ev.type}-${i}`}
                style={{
                  flexDirection: "row",
                  alignItems: "flex-start",
                  paddingHorizontal: 14,
                  paddingVertical: 5,
                  borderBottomWidth: 1,
                  borderBottomColor: border,
                }}
              >
                <Text style={{ color: cfg.color, fontSize: 12, width: 18, fontWeight: "700" }}>
                  {cfg.icon}
                </Text>
                <Text
                  style={{ color: textColor, fontSize: 11, flex: 1, lineHeight: 16 }}
                  numberOfLines={2}
                >
                  <Text style={{ fontWeight: "600" }}>{ev.agent_id}</Text>{" "}
                  {formatEvent(ev)}
                </Text>
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}
