import { useEffect, useState } from "react";
import * as Location from "expo-location";

interface LocationState {
  location: { lng: number; lat: number } | null;
  error: string | null;
  loading: boolean;
}

export function useLocation(): LocationState {
  const [state, setState] = useState<LocationState>({
    location: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        if (!cancelled) {
          setState({ location: null, error: "Location permission denied", loading: false });
        }
        return;
      }

      try {
        const loc = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        if (!cancelled) {
          setState({
            location: { lng: loc.coords.longitude, lat: loc.coords.latitude },
            error: null,
            loading: false,
          });
        }
      } catch (e) {
        if (!cancelled) {
          setState({
            location: null,
            error: e instanceof Error ? e.message : "Failed to get location",
            loading: false,
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
