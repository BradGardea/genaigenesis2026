import { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import type { AgentSnapshot, SimulationConfig, TickMetrics } from "../services/simulationApi";
import type { AppTheme } from "../types/theme";

export type SimPanelState = "idle" | "created" | "running" | "completed" | "stopped";

export interface DisasterBbox {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

interface Props {
  theme: AppTheme;
  simState: SimPanelState;
  agents: AgentSnapshot[];
  metrics: TickMetrics | null;
  currentTick: number;
  maxTicks: number;
  error: string | null;
  onStart: (config: SimulationConfig) => void;
  onStop: () => void;
  disasterBbox?: DisasterBbox | null;
}

const STATE_COLORS: Record<string, string> = {
  idle: "#94A3B8",
  planning: "#FBBF24",
  evacuating: "#60A5FA",
  arrived: "#34D399",
  sheltering: "#FB923C",
};

const AGENT_STATE_ICONS: Record<string, string> = {
  idle: "●",
  planning: "◐",
  evacuating: "→",
  arrived: "✓",
  sheltering: "⌂",
};

// Default LA bounding box
const DEFAULT_CONFIG: SimulationConfig = {
  num_evacuees: 8,
  bbox_min_lat: 34.0,
  bbox_max_lat: 34.1,
  bbox_min_lng: -118.35,
  bbox_max_lng: -118.20,
  destination_lat: 34.05,
  destination_lng: -118.10,
  tick_interval_seconds: 2.0,
  virtual_seconds_per_tick: 120.0,
  max_ticks: 20,
};

export function SimulationPanel({
  theme,
  simState,
  agents,
  metrics,
  currentTick,
  maxTicks,
  error,
  onStart,
  onStop,
  disasterBbox,
}: Props) {
  const isDark = theme === "dark";
  const [collapsed, setCollapsed] = useState(false);
  const [numAgents, setNumAgents] = useState(DEFAULT_CONFIG.num_evacuees);
  const [maxTicksInput, setMaxTicksInput] = useState(String(DEFAULT_CONFIG.max_ticks));
  const [destLat, setDestLat] = useState(String(DEFAULT_CONFIG.destination_lat));
  const [destLng, setDestLng] = useState(String(DEFAULT_CONFIG.destination_lng));

  const hasDisaster = !!disasterBbox;

  const isActive = simState === "running" || simState === "created";
  const isDone = simState === "completed" || simState === "stopped";

  const bg = isDark ? "rgba(15,23,42,0.92)" : "rgba(255,255,255,0.94)";
  const border = isDark ? "#334155" : "#e2e8f0";
  const textPrimary = isDark ? "#f1f5f9" : "#0f172a";
  const textMuted = isDark ? "#94a3b8" : "#64748b";
  const accentBg = isDark ? "#1e3a5f" : "#eff6ff";
  const accentText = isDark ? "#93c5fd" : "#1d4ed8";

  function handleStart() {
    const cfg: SimulationConfig = {
      ...DEFAULT_CONFIG,
      num_evacuees: numAgents,
      max_ticks: parseInt(maxTicksInput) || 20,
      destination_lat: parseFloat(destLat) || DEFAULT_CONFIG.destination_lat,
      destination_lng: parseFloat(destLng) || DEFAULT_CONFIG.destination_lng,
    };

    // Override bbox from disaster step data when available
    if (disasterBbox) {
      cfg.bbox_min_lat = disasterBbox.minLat;
      cfg.bbox_max_lat = disasterBbox.maxLat;
      cfg.bbox_min_lng = disasterBbox.minLng;
      cfg.bbox_max_lng = disasterBbox.maxLng;
    }

    onStart(cfg);
  }

  const progressPct = maxTicks > 0 ? Math.round((currentTick / maxTicks) * 100) : 0;

  return (
    <View
      style={{
        width: 220,
        borderRadius: 10,
        overflow: "hidden",
        borderWidth: 1,
        borderColor: border,
        backgroundColor: bg,
        backdropFilter: "blur(8px)",
      } as any}
    >
      {/* Header */}
      <Pressable
        onPress={() => setCollapsed((v) => !v)}
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          paddingHorizontal: 10,
          paddingVertical: 7,
          borderBottomWidth: collapsed ? 0 : 1,
          borderBottomColor: border,
        }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View
            style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              backgroundColor: isActive ? "#34D399" : isDone ? "#60A5FA" : "#94A3B8",
            }}
          />
          <Text style={{ fontSize: 12, fontWeight: "700", color: textPrimary }}>
            Multi-Agent Sim
          </Text>
        </View>
        <Text style={{ fontSize: 11, color: textMuted }}>{collapsed ? "▲" : "▼"}</Text>
      </Pressable>

      {!collapsed && (
        <View style={{ padding: 10, gap: 8 }}>
          {/* Running: live metrics HUD */}
          {isActive && metrics && (
            <>
              {/* Progress bar */}
              <View>
                <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 3 }}>
                  <Text style={{ fontSize: 10, color: textMuted }}>Tick {currentTick} / {maxTicks}</Text>
                  <Text style={{ fontSize: 10, color: accentText }}>{progressPct}%</Text>
                </View>
                <View style={{ height: 4, backgroundColor: isDark ? "#1e293b" : "#e2e8f0", borderRadius: 2 }}>
                  <View
                    style={{
                      height: 4,
                      width: `${progressPct}%`,
                      backgroundColor: "#60A5FA",
                      borderRadius: 2,
                    }}
                  />
                </View>
              </View>

              {/* Agent state grid */}
              <View style={{ gap: 4 }}>
                {(["evacuating", "arrived", "idle", "sheltering", "planning"] as const).map((state) => {
                  const key = `agents_${state}` as keyof TickMetrics;
                  const count = (metrics[key] as number) ?? 0;
                  if (count === 0) return null;
                  return (
                    <View key={state} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: STATE_COLORS[state] }} />
                      <Text style={{ fontSize: 11, color: textPrimary, flex: 1, textTransform: "capitalize" }}>{state}</Text>
                      <Text style={{ fontSize: 11, fontWeight: "700", color: textPrimary }}>{count}</Text>
                    </View>
                  );
                })}
              </View>

              {/* Stats row */}
              <View
                style={{
                  flexDirection: "row",
                  gap: 6,
                  paddingTop: 6,
                  borderTopWidth: 1,
                  borderTopColor: border,
                }}
              >
                <View style={{ flex: 1, alignItems: "center", padding: 4, backgroundColor: isDark ? "#1e293b" : "#f8fafc", borderRadius: 6 }}>
                  <Text style={{ fontSize: 11, fontWeight: "700", color: textPrimary }}>
                    {metrics.reroutes_this_tick}
                  </Text>
                  <Text style={{ fontSize: 9, color: textMuted }}>reroutes</Text>
                </View>
                <View style={{ flex: 1, alignItems: "center", padding: 4, backgroundColor: isDark ? "#1e293b" : "#f8fafc", borderRadius: 6 }}>
                  <Text style={{ fontSize: 11, fontWeight: "700", color: metrics.active_hazards > 0 ? "#f87171" : textPrimary }}>
                    {metrics.active_hazards}
                  </Text>
                  <Text style={{ fontSize: 9, color: textMuted }}>hazards</Text>
                </View>
                <View style={{ flex: 1, alignItems: "center", padding: 4, backgroundColor: isDark ? "#1e293b" : "#f8fafc", borderRadius: 6 }}>
                  <Text style={{ fontSize: 11, fontWeight: "700", color: textPrimary }}>
                    {Math.round(metrics.avg_congestion * 100)}%
                  </Text>
                  <Text style={{ fontSize: 9, color: textMuted }}>congestion</Text>
                </View>
              </View>

              {/* Stop button */}
              <Pressable
                onPress={onStop}
                style={{ backgroundColor: "#ef4444", borderRadius: 6, paddingVertical: 6, alignItems: "center" }}
              >
                <Text style={{ fontSize: 11, fontWeight: "700", color: "#fff" }}>■ Stop</Text>
              </Pressable>
            </>
          )}

          {/* Completed/stopped summary */}
          {isDone && metrics && (
            <>
              <View style={{ backgroundColor: accentBg, borderRadius: 6, padding: 8, gap: 3 }}>
                <Text style={{ fontSize: 11, fontWeight: "700", color: accentText }}>
                  {simState === "completed" ? "✓ Completed" : "Stopped"} — {currentTick} ticks
                </Text>
                <Text style={{ fontSize: 11, color: textPrimary }}>
                  {metrics.agents_arrived} arrived · {metrics.agents_sheltering} sheltering
                </Text>
              </View>
              <Pressable
                onPress={handleStart}
                style={{ backgroundColor: accentText, borderRadius: 6, paddingVertical: 6, alignItems: "center" }}
              >
                <Text style={{ fontSize: 11, fontWeight: "700", color: "#fff" }}>▶ Run Again</Text>
              </Pressable>
            </>
          )}

          {/* Idle: config + start */}
          {simState === "idle" && (
            <>
              {/* Agents */}
              <View>
                <Text style={{ fontSize: 10, fontWeight: "600", color: textMuted, marginBottom: 3 }}>
                  AGENTS: {numAgents}
                </Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Pressable
                    onPress={() => setNumAgents((v) => Math.max(1, v - 1))}
                    style={{ width: 24, height: 24, borderRadius: 4, backgroundColor: isDark ? "#1e293b" : "#f1f5f9", alignItems: "center", justifyContent: "center" }}
                  >
                    <Text style={{ color: textPrimary, fontSize: 14 }}>−</Text>
                  </Pressable>
                  <View style={{ flex: 1, height: 4, backgroundColor: isDark ? "#1e293b" : "#e2e8f0", borderRadius: 2 }}>
                    <View style={{ height: 4, width: `${(numAgents / 20) * 100}%`, backgroundColor: "#60A5FA", borderRadius: 2 }} />
                  </View>
                  <Pressable
                    onPress={() => setNumAgents((v) => Math.min(20, v + 1))}
                    style={{ width: 24, height: 24, borderRadius: 4, backgroundColor: isDark ? "#1e293b" : "#f1f5f9", alignItems: "center", justifyContent: "center" }}
                  >
                    <Text style={{ color: textPrimary, fontSize: 14 }}>+</Text>
                  </Pressable>
                </View>
              </View>

              {/* Max ticks */}
              <View>
                <Text style={{ fontSize: 10, fontWeight: "600", color: textMuted, marginBottom: 3 }}>MAX TICKS</Text>
                <TextInput
                  value={maxTicksInput}
                  onChangeText={setMaxTicksInput}
                  keyboardType="numeric"
                  style={{
                    fontSize: 12,
                    color: textPrimary,
                    backgroundColor: isDark ? "#1e293b" : "#f8fafc",
                    borderRadius: 6,
                    paddingHorizontal: 8,
                    paddingVertical: 4,
                    borderWidth: 1,
                    borderColor: border,
                  }}
                />
              </View>

              {/* Destination */}
              <View>
                <Text style={{ fontSize: 10, fontWeight: "600", color: textMuted, marginBottom: 3 }}>DEST (lat, lng)</Text>
                <View style={{ flexDirection: "row", gap: 4 }}>
                  <TextInput
                    value={destLat}
                    onChangeText={setDestLat}
                    placeholder="lat"
                    placeholderTextColor={textMuted}
                    style={{
                      flex: 1, fontSize: 11, color: textPrimary,
                      backgroundColor: isDark ? "#1e293b" : "#f8fafc",
                      borderRadius: 6, paddingHorizontal: 6, paddingVertical: 4,
                      borderWidth: 1, borderColor: border,
                    }}
                  />
                  <TextInput
                    value={destLng}
                    onChangeText={setDestLng}
                    placeholder="lng"
                    placeholderTextColor={textMuted}
                    style={{
                      flex: 1, fontSize: 11, color: textPrimary,
                      backgroundColor: isDark ? "#1e293b" : "#f8fafc",
                      borderRadius: 6, paddingHorizontal: 6, paddingVertical: 4,
                      borderWidth: 1, borderColor: border,
                    }}
                  />
                </View>
              </View>

              {hasDisaster && (
                <View style={{ backgroundColor: isDark ? "#422006" : "#fef3c7", borderRadius: 6, padding: 6 }}>
                  <Text style={{ fontSize: 10, fontWeight: "600", color: isDark ? "#fbbf24" : "#92400e" }}>
                    Using disaster area for agent spawn
                  </Text>
                </View>
              )}

              {error && (
                <Text style={{ fontSize: 10, color: "#f87171" }}>{error}</Text>
              )}

              <Pressable
                onPress={handleStart}
                style={{ backgroundColor: "#2563eb", borderRadius: 6, paddingVertical: 7, alignItems: "center" }}
              >
                <Text style={{ fontSize: 12, fontWeight: "700", color: "#fff" }}>▶ Start Simulation</Text>
              </Pressable>
            </>
          )}

          {/* Loading */}
          {simState === "created" && !metrics && (
            <Text style={{ fontSize: 11, color: textMuted, textAlign: "center" }}>Initializing agents…</Text>
          )}

          {/* Legend */}
          {(isActive || isDone) && (
            <View style={{ paddingTop: 4, borderTopWidth: 1, borderTopColor: border, gap: 3 }}>
              <Text style={{ fontSize: 9, fontWeight: "600", color: textMuted, letterSpacing: 0.5 }}>LEGEND</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4 }}>
                {Object.entries(STATE_COLORS).map(([state, color]) => (
                  <View key={state} style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
                    <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: color }} />
                    <Text style={{ fontSize: 9, color: textMuted, textTransform: "capitalize" }}>{state}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </View>
      )}
    </View>
  );
}
