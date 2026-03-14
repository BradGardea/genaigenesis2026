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

  const fetchRoute = useCallback(async () => {
    if (!origin || !destination) return;

    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const route = await requestRoute(origin, destination, profile);
      setState((s) => ({ ...s, route, loading: false, error: null, rerouting: false }));

      esRef.current?.close();

      const es = subscribeToRouteUpdates(route.route_id, async (event) => {
        if (event.type === "reroute") {
          setState((s) => ({ ...s, rerouting: true }));
          try {
            const rerouteOrigin =
              tripActiveRef.current && currentPosRef.current
                ? currentPosRef.current
                : origin;
            const newRoute = await requestRoute(rerouteOrigin, destination, profile);
            setState((s) => ({ ...s, route: newRoute, loading: false, error: null, rerouting: false }));
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
