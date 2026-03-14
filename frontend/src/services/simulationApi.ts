const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Simulation API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export type AgentState = "idle" | "planning" | "evacuating" | "arrived" | "sheltering";
export type SimState = "created" | "running" | "completed" | "stopped";

export interface AgentSnapshot {
  agent_id: string;
  state: AgentState;
  lat: number;
  lng: number;
  family_size: number;
  vehicles: number;
  route_id: string | null;
  route_geometry: [number, number][] | null;
  progress: number;
  last_decision: { action: string; reasoning: string; urgency: number } | null;
}

export interface TickMetrics {
  tick: number;
  agents_idle: number;
  agents_planning: number;
  agents_evacuating: number;
  agents_arrived: number;
  agents_sheltering: number;
  reroutes_this_tick: number;
  active_hazards: number;
  avg_congestion: number;
}

export interface SimulationStatus {
  sim_id: string;
  state: SimState;
  current_tick: number;
  max_ticks: number;
  agents: AgentSnapshot[];
  latest_metrics: TickMetrics | null;
}

export interface SimulationConfig {
  num_evacuees: number;
  bbox_min_lat: number;
  bbox_max_lat: number;
  bbox_min_lng: number;
  bbox_max_lng: number;
  destination_lat: number;
  destination_lng: number;
  tick_interval_seconds: number;
  virtual_seconds_per_tick: number;
  max_ticks: number;
  watsonx_model_id?: string;
}

export function createSimulation(config: SimulationConfig): Promise<{ sim_id: string; state: string; num_agents: number }> {
  return request("/simulation/create", { method: "POST", body: JSON.stringify(config) });
}

export function startSimulation(simId: string): Promise<{ sim_id: string; state: string }> {
  return request(`/simulation/${simId}/start`, { method: "POST" });
}

export function stopSimulation(simId: string): Promise<{ sim_id: string; state: string }> {
  return request(`/simulation/${simId}/stop`, { method: "POST" });
}

export function getSimulationStatus(simId: string): Promise<SimulationStatus> {
  return request(`/simulation/${simId}/status`);
}

export function subscribeToSimulation(
  simId: string,
  onTick: (metrics: TickMetrics) => void,
  onHazard: (data: { hazard_id: string; tick: number; type: string }) => void,
  onEnd: () => void,
): () => void {
  const es = new EventSource(`${API_BASE}/simulation/${simId}/stream`);

  es.addEventListener("tick", (e: MessageEvent) => {
    try { onTick(JSON.parse(e.data)); } catch { /* ignore */ }
  });
  es.addEventListener("hazard_injected", (e: MessageEvent) => {
    try { onHazard(JSON.parse(e.data)); } catch { /* ignore */ }
  });
  es.addEventListener("simulation_end", () => {
    es.close();
    onEnd();
  });
  es.onerror = () => { /* SSE auto-reconnects */ };

  return () => es.close();
}
