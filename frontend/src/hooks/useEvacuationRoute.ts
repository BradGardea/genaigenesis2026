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
  tripActive: boolean;
  currentPosition: Coordinate | null;
}

export interface EvacuationRouteControls extends EvacuationRouteState {
  refetch: () => void;
  startTrip: () => void;
  endTrip: () => void;
  setCurrentPosition: (coord: Coordinate) => void;
  setRouteDirectly: (route: RouteResponse) => void;
  setRerouting: (value: boolean) => void;
}

export function useEvacuationRoute(
  origin: Coordinate | null,
  destination: Coordinate | null,
  profile?: RouteRequest["profile"]
): EvacuationRouteControls {
  const [state, setState] = useState<EvacuationRouteState>({
    route: null,
    loading: false,
    error: null,
    rerouting: false,
    tripActive: false,
    currentPosition: null,
  });

  const esRef = useRef<EventSource | null>(null);
  const tripActiveRef = useRef(false);
  const currentPosRef = useRef<Coordinate | null>(null);

  // ---------------------------------------------------------------------------
  // SSE subscription helper stored in a ref so it can recursively re-subscribe
  // when a reroute produces a new route_id.
  // ---------------------------------------------------------------------------
  const setupSSERef = useRef<(routeId: string) => void>(undefined);

  setupSSERef.current = (routeId: string) => {
    esRef.current?.close();

    const es = subscribeToRouteUpdates(routeId, async (event) => {
      if (event.type === "reroute") {
        setState((s) => ({ ...s, rerouting: true }));
        try {
          // Always reroute from the user's current position when available
          const rerouteOrigin = currentPosRef.current ?? origin;
          if (!rerouteOrigin || !destination) return;

          const newRoute = await requestRoute(rerouteOrigin, destination, profile);
          setState((s) => ({ ...s, route: newRoute, loading: false, error: null, rerouting: false }));

          // Re-subscribe SSE to the NEW route's stream
          setupSSERef.current?.(newRoute.route_id);
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
  };

  const fetchRoute = useCallback(async () => {
    if (!origin || !destination) return;

    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      // Always use current position as origin when available (disaster demo or
      // active trip), falling back to the fixed origin for the initial request.
      const routeOrigin = currentPosRef.current ?? origin;
      const route = await requestRoute(routeOrigin, destination, profile);
      setState((s) => ({ ...s, route, loading: false, error: null, rerouting: false }));

      // Subscribe to SSE for this route (closes any previous subscription)
      setupSSERef.current?.(route.route_id);
    } catch (err) {
      setState((s) => ({
        ...s,
        route: null,
        loading: false,
        error: err instanceof Error ? err.message : "Route request failed",
        rerouting: false,
      }));
    }
  }, [origin, destination, profile]);

  useEffect(() => {
    fetchRoute();
    return () => {
      esRef.current?.close();
    };
  }, [fetchRoute]);

  const startTrip = useCallback(() => {
    if (!origin) return;
    tripActiveRef.current = true;
    currentPosRef.current = origin;
    setState((s) => ({ ...s, tripActive: true, currentPosition: origin }));
  }, [origin]);

  const endTrip = useCallback(() => {
    tripActiveRef.current = false;
    currentPosRef.current = null;
    esRef.current?.close();
    esRef.current = null;
    setState((s) => ({ ...s, tripActive: false, currentPosition: null }));
  }, []);

  const setCurrentPosition = useCallback((coord: Coordinate) => {
    currentPosRef.current = coord;
    setState((s) => ({ ...s, currentPosition: coord }));
  }, []);

  const setRouteDirectly = useCallback((route: RouteResponse) => {
    setState((s) => ({ ...s, route, loading: false, error: null, rerouting: false }));
  }, []);

  const setRerouting = useCallback((value: boolean) => {
    setState((s) => ({ ...s, rerouting: value }));
  }, []);

  return {
    ...state,
    refetch: fetchRoute,
    startTrip,
    endTrip,
    setCurrentPosition,
    setRouteDirectly,
    setRerouting,
  };
}
