import {
  Coordinate,
  HazardReport,
  HazardZone,
  RouteRequest,
  RouteResponse,
  RouteWeatherPoint,
  WeatherAlertCollection,
} from "../types/domain";

const API_BASE = "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function reportHazard(
  hazardType: string,
  location: Coordinate,
  description: string = "",
  radiusMeters?: number
): Promise<HazardZone> {
  const body: HazardReport = {
    hazard_type: hazardType,
    location,
    description,
    ...(radiusMeters != null && { radius_meters: radiusMeters }),
  };
  return request<HazardZone>("/hazards/report", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getActiveHazards(): Promise<HazardZone[]> {
  return request<HazardZone[]>("/hazards/active");
}

export async function deactivateHazard(hazardId: string): Promise<void> {
  await request(`/hazards/${hazardId}`, { method: "DELETE" });
}

export function requestRoute(
  origin: Coordinate,
  destination: Coordinate,
  profile?: RouteRequest["profile"]
): Promise<RouteResponse> {
  const body: RouteRequest = { origin, destination, profile };
  return request<RouteResponse>("/routes/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function subscribeToRouteUpdates(
  routeId: string,
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void
): EventSource {
  const es = new EventSource(`${API_BASE}/routes/${routeId}/stream`);
  const parseEventData = (raw: string): Record<string, unknown> => {
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return { raw };
    }
  };

  es.addEventListener("reroute", (e) => {
    onEvent({ type: "reroute", data: parseEventData(e.data) });
  });

  es.addEventListener("hazard_added", (e) => {
    onEvent({ type: "hazard_added", data: parseEventData(e.data) });
  });

  es.addEventListener("hazard_removed", (e) => {
    onEvent({ type: "hazard_removed", data: parseEventData(e.data) });
  });

  es.onerror = () => {
    // EventSource auto-reconnects by default
  };

  return es;
}

export function fetchWeatherZones(): Promise<WeatherAlertCollection> {
  return request<WeatherAlertCollection>("/events/weather-zones");
}

export function fetchRouteWeather(routeId: string): Promise<RouteWeatherPoint[]> {
  return request<RouteWeatherPoint[]>(`/routes/${routeId}/weather`);
}
