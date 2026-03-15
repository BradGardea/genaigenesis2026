import { Coordinate, RouteResponse } from "../types/domain";
import { reportHazard, requestRoute } from "../services/api";
import { getPointAlongRoute, haversineDistance } from "../hooks/useTripSimulation";

const DEMO_ORIGIN: Coordinate = { lat: 43.706, lng: -79.41 };
const DEMO_DESTINATION: Coordinate = { lat: 43.65, lng: -79.38 };

const HAZARD_FRACTION = 0.35;
const HAZARD_APPROACH_METERS = 800;
const HAZARD_RADIUS_METERS = 200;

export interface DemoControls {
  setOriginText: (text: string) => void;
  setDestText: (text: string) => void;
  setOrigin: (coord: Coordinate) => void;
  setDestination: (coord: Coordinate) => void;
  startTrip: () => void;
  endTrip: () => void;
  refetch: () => void;
  setRouteDirectly: (route: RouteResponse) => void;
  setRerouting: (value: boolean) => void;
  pauseSimulation: () => void;
  fetchHazards: () => void;
  setDemoStatus: (status: string) => void;
  fitMapToRoute: (route: RouteResponse) => void;
  getCurrentPosition: () => Coordinate | null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatCoord(c: Coordinate): string {
  return `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`;
}

function formatEta(seconds: number): string {
  const mins = Math.round(seconds / 60);
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

/**
 * Poll until the car is within `thresholdMeters` of `target`.
 * Resolves as soon as the distance drops below the threshold (or timeout).
 */
function waitUntilNear(
  getCurrentPosition: () => Coordinate | null,
  target: Coordinate,
  thresholdMeters: number,
  timeoutMs = 120_000
): Promise<void> {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = () => {
      const pos = getCurrentPosition();
      if (pos && haversineDistance(pos, target) < thresholdMeters) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) {
        resolve();
        return;
      }
      setTimeout(check, 200);
    };
    check();
  });
}

export async function runDemo(controls: DemoControls): Promise<void> {
  const {
    setOriginText,
    setDestText,
    setOrigin,
    setDestination,
    startTrip,
    endTrip,
    setRouteDirectly,
    setRerouting,
    pauseSimulation,
    fetchHazards,
    setDemoStatus,
    fitMapToRoute,
    getCurrentPosition,
  } = controls;

  try {
    setDemoStatus("Setting origin and destination...");
    setOriginText(formatCoord(DEMO_ORIGIN));
    setDestText(formatCoord(DEMO_DESTINATION));
    setOrigin(DEMO_ORIGIN);
    setDestination(DEMO_DESTINATION);
    await sleep(1200);

    setDemoStatus("Planning traffic-aware evacuation route...");
    const route = await requestRoute(DEMO_ORIGIN, DEMO_DESTINATION);
    setRouteDirectly(route);
    fitMapToRoute(route);
    const eta = formatEta(route.duration_seconds);
    const dist = (route.distance_meters / 1000).toFixed(1);
    setDemoStatus(`Route planned — ${dist} km, ETA ${eta} (crisis-adjusted)`);
    await sleep(3000);

    setDemoStatus("Starting trip — following route...");
    startTrip();

    if (route.geometry && route.geometry.coordinates.length > 1) {
      const hazardCoord = getPointAlongRoute(route.geometry, HAZARD_FRACTION);

      setDemoStatus("Driving along route...");
      await waitUntilNear(getCurrentPosition, hazardCoord, HAZARD_APPROACH_METERS);

      // Freeze the car INSTANTLY via ref (no React re-render lag)
      pauseSimulation();
      setRerouting(true);
      setDemoStatus("⚠ Roadblock reported ahead — rerouting...");

      // Register the hazard FIRST so the backend can avoid it
      await reportHazard("roadblock", hazardCoord, "Demo: roadblock on road", HAZARD_RADIUS_METERS);
      fetchHazards();

      // NOW request a route that avoids the registered hazard
      const currentPos = getCurrentPosition();
      const rerouteOrigin = currentPos ?? DEMO_ORIGIN;
      const newRoute = await requestRoute(rerouteOrigin, DEMO_DESTINATION);

      // setRouteDirectly clears rerouting; geometry change resets manualPause
      setRouteDirectly(newRoute);
      const newEta = formatEta(newRoute.duration_seconds);
      const newDist = (newRoute.distance_meters / 1000).toFixed(1);
      setDemoStatus(`Rerouted — ${newDist} km, ETA ${newEta} (crisis-adjusted)`);
      await sleep(4000);
      setDemoStatus("Following rerouted path...");
      await sleep(11000);
    }

    setDemoStatus("");
    endTrip();
    await sleep(1500);
    setDemoStatus("");
  } catch (err) {
    setDemoStatus(`Demo error: ${err instanceof Error ? err.message : "unknown"}`);
    await sleep(3000);
    setDemoStatus("");
  }
}
