import { useCallback, useEffect, useRef, useState } from "react";
import {
  Coordinate,
  RouteRequest,
  RouteResponse,
} from "../types/domain";
import { requestRoute, subscribeToRouteUpdates } from "../services/api";

interface EvacuationRouteState {
  route: RouteResponse | null;
  loading: boolean;
  error: string | null;
  rerouting: boolean;
}

export function useEvacuationRoute(
  origin: Coordinate | null,
  destination: Coordinate | null,
  profile?: RouteRequest["profile"]
): EvacuationRouteState & { refetch: () => void } {
  const [state, setState] = useState<EvacuationRouteState>({
    route: null,
    loading: false,
    error: null,
    rerouting: false,
  });

  const esRef = useRef<EventSource | null>(null);

  const fetchRoute = useCallback(async () => {
    if (!origin || !destination) return;

    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const route = await requestRoute(origin, destination, profile);
      setState({ route, loading: false, error: null, rerouting: false });

      // Close previous SSE connection
      esRef.current?.close();

      // Open SSE subscription for live reroutes
      const es = subscribeToRouteUpdates(route.route_id, async (event) => {
        if (event.type === "reroute") {
          setState((s) => ({ ...s, rerouting: true }));
          try {
            const newRoute = await requestRoute(origin, destination, profile);
            setState({ route: newRoute, loading: false, error: null, rerouting: false });
          } catch (err) {
            setState((s) => ({
              ...s,
              rerouting: false,
              error: err instanceof Error ? err.message : "Reroute failed",
            }));
          }
        }
      });
      esRef.current = es;
    } catch (err) {
      setState({
        route: null,
        loading: false,
        error: err instanceof Error ? err.message : "Route request failed",
        rerouting: false,
      });
    }
  }, [origin, destination, profile]);

  useEffect(() => {
    fetchRoute();
    return () => {
      esRef.current?.close();
    };
  }, [fetchRoute]);

  return { ...state, refetch: fetchRoute };
}
