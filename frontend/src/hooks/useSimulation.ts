import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  AgentSnapshot,
  SimState,
  SimulationConfig,
  SimulationStatus,
  TickMetrics,
  createSimulation,
  getSimulationStatus,
  startSimulation,
  stopSimulation,
  subscribeToSimulation,
} from "../services/simulationApi";

export interface SimulationControls {
  simId: string | null;
  simState: SimState | "idle";
  agents: AgentSnapshot[];
  metrics: TickMetrics | null;
  currentTick: number;
  maxTicks: number;
  agentEvents: AgentEvent[];
  createAndStart: (config: SimulationConfig) => Promise<void>;
  stop: () => Promise<void>;
  error: string | null;
}

export function useSimulation(): SimulationControls {
  const [simId, setSimId] = useState<string | null>(null);
  const [simState, setSimState] = useState<SimState | "idle">("idle");
  const [agents, setAgents] = useState<AgentSnapshot[]>([]);
  const [metrics, setMetrics] = useState<TickMetrics | null>(null);
  const [currentTick, setCurrentTick] = useState(0);
  const [maxTicks, setMaxTicks] = useState(72);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const unsubRef = useRef<(() => void) | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll agent positions while running (SSE only carries metrics)
  const pollOnce = useCallback(async (id: string) => {
    try {
      const status: SimulationStatus = await getSimulationStatus(id);
      setAgents(status.agents);
      setCurrentTick(status.current_tick);
      // Always sync metrics from polling so stats stay fresh even if SSE lags
      if (status.latest_metrics) {
        setMetrics(status.latest_metrics);
      }
      if (status.state !== "running") {
        setSimState(status.state);
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      }
    } catch (err) { console.warn("[useSimulation] poll failed:", err); }
  }, []);

  const startPolling = useCallback((id: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    // Immediate first poll so routes/positions appear without delay
    pollOnce(id);
    pollRef.current = setInterval(() => pollOnce(id), 2000);
  }, [pollOnce]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => () => { stopPolling(); unsubRef.current?.(); }, [stopPolling]);

  // Auto-reset to idle when simulation ends so config form reappears
  useEffect(() => {
    if (simState === "completed" || simState === "stopped") {
      const timer = setTimeout(() => setSimState("idle"), 1500);
      return () => clearTimeout(timer);
    }
  }, [simState]);

  const createAndStart = useCallback(async (config: SimulationConfig) => {
    setError(null);
    try {
      // Stop any existing simulation
      if (simId) {
        try { await stopSimulation(simId); } catch { /* ignore */ }
      }
      unsubRef.current?.();
      stopPolling();
      setAgents([]);
      setMetrics(null);
      setCurrentTick(0);
      setAgentEvents([]);

      const { sim_id } = await createSimulation(config);
      setSimId(sim_id);
      setMaxTicks(config.max_ticks);
      setSimState("created");

      await startSimulation(sim_id);
      setSimState("running");

      // Subscribe to SSE tick events for live metrics
      const unsub = subscribeToSimulation(
        sim_id,
        (tick) => {
          setMetrics(tick);
          setCurrentTick(tick.tick);
        },
        (_hazard) => { /* hazard injected — agents will reroute */ },
        () => {
          setSimState("completed");
          stopPolling();
        },
        (data) => {
          setAgentEvents((prev) => {
            const merged = [...data.events, ...prev];
            return merged.length > 200 ? merged.slice(0, 200) : merged;
          });
        },
      );
      unsubRef.current = unsub;

      // Poll agent positions separately
      startPolling(sim_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
      setSimState("idle");
    }
  }, [simId, startPolling, stopPolling]);

  const stop = useCallback(async () => {
    if (!simId) return;
    try {
      await stopSimulation(simId);
      setSimState("stopped");
    } catch { /* ignore */ } finally {
      unsubRef.current?.();
      stopPolling();
    }
  }, [simId, stopPolling]);

  return { simId, simState, agents, metrics, currentTick, maxTicks, agentEvents, createAndStart, stop, error };
}
