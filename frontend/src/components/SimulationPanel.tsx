import { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import type { AgentSnapshot, ClusterSummary, SimulationConfig, TickMetrics } from "../services/simulationApi";
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
  clusters?: ClusterSummary[];
  clusterColors?: Map<string, string>;
  disasterStepIndex?: number;
  disasterTotalSteps?: number;
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

// Default Vilankulo, Mozambique bounding box (matches disaster dataset)
const DEFAULT_CONFIG: SimulationConfig = {
  num_evacuees: 1,
  bbox_min_lat: -22.050,
  bbox_max_lat: -21.960,
  bbox_min_lng: 35.270,
  bbox_max_lng: 35.330,
  destination_lat: -22.000,
  destination_lng: 35.200,
  tick_interval_seconds: 2.0,
  virtual_seconds_per_tick: 120.0,
  max_ticks: 72,
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
  clusters,
  clusterColors,
  disasterStepIndex,
  disasterTotalSteps,
}: Props) {
  const isDark = theme === "dark";
  const [collapsed, setCollapsed] = useState(false);
  const [numAgents, setNumAgents] = useState(DEFAULT_CONFIG.num_evacuees);
  const [maxTicksInput, setMaxTicksInput] = useState(String(DEFAULT_CONFIG.max_ticks));
  const [clusterRadiusM, setClusterRadiusM] = useState("500");

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
      max_ticks: parseInt(maxTicksInput) || 72,
      cluster_radius_m: parseFloat(clusterRadiusM) || 500,
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

              {/* Disaster step indicator */}
              {disasterTotalSteps != null && disasterTotalSteps > 0 && (
                <View>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 3 }}>
                    <Text style={{ fontSize: 10, color: textMuted }}>
                      Disaster Step {(disasterStepIndex ?? 0) + 1} / {disasterTotalSteps}
                    </Text>
                    <Text style={{ fontSize: 10, color: "#f87171" }}>
                      {Math.round(((disasterStepIndex ?? 0) + 1) / disasterTotalSteps * 100)}%
                    </Text>
                  </View>
                  <View style={{ height: 4, backgroundColor: isDark ? "#1e293b" : "#e2e8f0", borderRadius: 2 }}>
                    <View
                      style={{
                        height: 4,
                        width: `${Math.round(((disasterStepIndex ?? 0) + 1) / disasterTotalSteps * 100)}%`,
                        backgroundColor: "#f87171",
                        borderRadius: 2,
                      }}
                    />
                  </View>
                </View>
              )}

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

              {/* Single-agent focus card */}
              {agents.length === 1 && agents[0] && (
                <View style={{ backgroundColor: isDark ? "#1e293b" : "#f0f9ff", borderRadius: 8, padding: 8, gap: 4, borderWidth: 1, borderColor: isDark ? "#334155" : "#bfdbfe" }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: "#3b82f6", alignItems: "center", justifyContent: "center" }}>
                      <Text style={{ fontSize: 12, color: "#fff", fontWeight: "700" }}>
                        {(agents[0].name ?? "?")[0]}
                      </Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: "700", color: textPrimary }}>
                        {agents[0].name || agents[0].agent_id}
                      </Text>
                      <Text style={{ fontSize: 9, color: STATE_COLORS[agents[0].state] ?? textMuted, textTransform: "capitalize", fontWeight: "600" }}>
                        {AGENT_STATE_ICONS[agents[0].state] ?? "?"} {agents[0].state}
                      </Text>
                    </View>
                  </View>
                  {agents[0].scenario ? (
                    <Text style={{ fontSize: 9, color: textMuted, fontStyle: "italic" }}>
                      "{agents[0].scenario}"
                    </Text>
                  ) : null}
                  {agents[0].dest_name ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 }}>
                      <Text style={{ fontSize: 9, color: textMuted }}>→</Text>
                      <Text style={{ fontSize: 10, fontWeight: "600", color: accentText }}>{agents[0].dest_name}</Text>
                    </View>
                  ) : null}
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 2 }}>
                    <Text style={{ fontSize: 9, color: textMuted }}>
                      Progress: {Math.round((agents[0].progress ?? 0) * 100)}%
                    </Text>
                    <Text style={{ fontSize: 9, color: textMuted }}>
                      Family: {agents[0].family_size} · Cars: {agents[0].vehicles}
                    </Text>
                  </View>
                </View>
              )}

              {/* Cluster legend (multi-agent) */}
              {agents.length > 1 && clusters && clusters.length > 0 && (
                <View style={{ paddingTop: 4, gap: 3 }}>
                  <Text style={{ fontSize: 10, fontWeight: "600", color: textMuted }}>
                    CLUSTERS ({clusters.length})
                  </Text>
                  {clusters.map((c) => {
                    const color = clusterColors?.get(c.cluster_id) ?? "#6366F1";
                    const leaderAgent = agents.find((a) => a.agent_id === c.leader_id);
                    const leaderState = leaderAgent?.state ?? "?";
                    return (
                      <View
                        key={c.cluster_id}
                        style={{
                          flexDirection: "row",
                          alignItems: "center",
                          gap: 5,
                          paddingVertical: 1,
                        }}
                      >
                        <View
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: 5,
                            backgroundColor: color,
                          }}
                        />
                        <Text style={{ fontSize: 10, color: textPrimary, flex: 1 }}>
                          {c.cluster_id.replace("cluster-", "C")}
                        </Text>
                        <Text style={{ fontSize: 10, color: textMuted }}>
                          ×{c.member_count}
                        </Text>
                        <Text
                          style={{
                            fontSize: 9,
                            color: STATE_COLORS[leaderState] ?? textMuted,
                            textTransform: "capitalize",
                          }}
                        >
                          {leaderState}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              )}

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
                <input
                  type="range"
                  min={1}
                  max={1500}
                  step={1}
                  value={numAgents}
                  onChange={(e) => setNumAgents(Number(e.target.value))}
                  style={{
                    width: "100%",
                    height: 4,
                    accentColor: "#60A5FA",
                    cursor: "pointer",
                  }}
                />
                <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 2 }}>
                  <Text style={{ fontSize: 9, color: textMuted }}>1</Text>
                  <Text style={{ fontSize: 9, color: textMuted }}>1500</Text>
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

              {/* Cluster radius */}
              <View>
                <Text style={{ fontSize: 10, fontWeight: "600", color: textMuted, marginBottom: 3 }}>CLUSTER RADIUS (m)</Text>
                <TextInput
                  value={clusterRadiusM}
                  onChangeText={setClusterRadiusM}
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

              {/* Evacuation points info */}
              <View style={{ backgroundColor: isDark ? "#1e293b" : "#f0fdf4", borderRadius: 6, padding: 6, gap: 2 }}>
                <Text style={{ fontSize: 10, fontWeight: "600", color: isDark ? "#86efac" : "#166534" }}>
                  5 evacuation points
                </Text>
                <Text style={{ fontSize: 9, color: textMuted }}>
                  Agents auto-route to nearest point
                </Text>
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
                accessibilityRole="button"
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
