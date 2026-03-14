import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Pressable, Text, TextInput, View } from "react-native";
import { mapIncidentPointsMock } from "../data";
import { AppTheme } from "../types/theme";
import {
  Coordinate,
  GeoJSONLineString,
  HazardZone,
  RouteResponse,
  RouteWeatherPoint,
} from "../types/domain";
import { useEvacuationRoute } from "../hooks/useEvacuationRoute";
import { useTripSimulation } from "../hooks/useTripSimulation";
import {
  getActiveHazards,
  fetchWeatherZones,
  fetchRouteWeather,
} from "../services/api";
import { ReportHazardModal } from "../components/ReportHazardModal";
import {
  WeatherLayerOverlay,
  WeatherLayerMode,
} from "../components/WeatherLayerOverlay";
import { runDemo, DemoControls } from "../demo/runDemo";
import { useDisasterDemo } from "../state/DisasterDemoContext";

interface MapScreenProps {
  theme: AppTheme;
}

const MAPBOX_PUBLIC_TOKEN = process.env.EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "";

const ROUTE_SOURCE = "evacuation-route";
const ROUTE_LAYER = "evacuation-route-line";
const HAZARD_SOURCE = "hazard-zones";
const HAZARD_FILL_LAYER = "hazard-zones-fill";
const HAZARD_OUTLINE_LAYER = "hazard-zones-outline";
const WIND_SOURCE = "gfs-wind";
const WIND_LAYER = "wind-particles";
const WEATHER_ALERT_SOURCE = "weather-alerts";
const WEATHER_ALERT_FILL = "weather-alerts-fill";
const WEATHER_ALERT_OUTLINE = "weather-alerts-outline";

const DEFAULT_CENTER: [number, number] = [-79.41, 43.706];
const SESSION_KEY = "crisisnet_route_session";

function coordFromText(text: string): Coordinate | null {
  const parts = text.split(",").map((s) => s.trim());
  if (parts.length !== 2) return null;
  const lat = parseFloat(parts[0]);
  const lng = parseFloat(parts[1]);
  if (isNaN(lat) || isNaN(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return { lat, lng };
}

function formatCoord(c: Coordinate): string {
  return `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`;
}

function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return `${hrs}h ${rem}m`;
}

function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

// ── Session persistence helpers ──────────────────────────────
interface SessionData {
  origin: Coordinate;
  destination: Coordinate;
  originText: string;
  destText: string;
  route: RouteResponse;
}

function saveSession(data: SessionData) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
  } catch {
    /* quota or private browsing */
  }
}

function loadSession(): SessionData | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SessionData;
  } catch {
    return null;
  }
}

function clearSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

// ── Car marker CSS (injected once) ────────────────────────────
const CAR_MARKER_CSS_ID = "crisisnet-car-marker-css";
function ensureCarMarkerCSS() {
  if (document.getElementById(CAR_MARKER_CSS_ID)) return;
  const style = document.createElement("style");
  style.id = CAR_MARKER_CSS_ID;
  style.textContent = `
    .crisisnet-car-marker {
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
    }
    .crisisnet-car-marker svg {
      width: 100%;
      height: 100%;
    }
  `;
  document.head.appendChild(style);
}

function createCarMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "crisisnet-car-marker";
  // Rotation is applied to the SVG child, not the outer element,
  // because Mapbox uses transform on the marker element for positioning.
  el.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"
        >
      <path d="M5 17h14v-5H5v5zm2.5-4a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5zm9 0a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5z" fill="#1e40af"/>
      <path d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16a1.5 1.5 0 0 1 0-3 1.5 1.5 0 0 1 0 3zm11 0a1.5 1.5 0 0 1 0-3 1.5 1.5 0 0 1 0 3zM5 11l1.5-4h11l1.5 4H5z" fill="#3b82f6"/>
    </svg>
  `;
  return el;
}

export function MapScreen({ theme }: MapScreenProps) {
  const isDark = theme === "dark";
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const originMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const destMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const positionMarkerRef = useRef<mapboxgl.Marker | null>(null);

  // ── Hydrate from session ───────────────────────────────────
  const saved = useMemo(() => loadSession(), []);

  const [originText, setOriginText] = useState(saved?.originText ?? "");
  const [destText, setDestText] = useState(saved?.destText ?? "");
  const [origin, setOrigin] = useState<Coordinate | null>(
    saved?.origin ?? null,
  );
  const [destination, setDestination] = useState<Coordinate | null>(
    saved?.destination ?? null,
  );
  const [hazardZones, setHazardZones] = useState<HazardZone[]>([]);
  const [hazardModalVisible, setHazardModalVisible] = useState(false);
  const [mapClickMode, setMapClickMode] = useState<
    "origin" | "destination" | null
  >(null);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoStatus, setDemoStatus] = useState("");
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapIsLoaded, setMapIsLoaded] = useState(false);

  const { weatherZones } = useDisasterDemo();

  // ── Weather layer state ──────────────────────────────────
  const [activeWeatherLayer, setActiveWeatherLayer] =
    useState<WeatherLayerMode>(null);

  // Set this to "wind" instead of null if you want the screenshot-style
  // wind layer to be on by default.
  const showWind = activeWeatherLayer === "wind";
  const showWeatherAlerts = activeWeatherLayer === "alerts";
  const showRouteWeather = activeWeatherLayer === "route-weather";
  const [routeWeatherPoints, setRouteWeatherPoints] = useState<
    RouteWeatherPoint[]
  >([]);
  const weatherMarkersRef = useRef<mapboxgl.Marker[]>([]);

  const {
    route,
    loading,
    error,
    rerouting,
    tripActive,
    currentPosition,
    refetch,
    startTrip,
    endTrip,
    setCurrentPosition,
    setRouteDirectly,
    setRerouting,
  } = useEvacuationRoute(origin, destination);

  // Restore persisted route on first render
  useEffect(() => {
    if (saved?.route && !route) {
      setRouteDirectly(saved.route);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [followCamera, setFollowCamera] = useState(true);

  // ── Trip simulation ────────────────────────────────────────
  const {
    position: simPosition,
    bearing: simBearing,
    progress: simProgress,
    pause: pauseSimulation,
  } = useTripSimulation(
    route?.geometry ?? null,
    route?.segment_durations,
    tripActive,
    20,
    rerouting,
  );

  const currentPositionRef = useRef<Coordinate | null>(null);
  currentPositionRef.current = currentPosition;

  useEffect(() => {
    if (simPosition && tripActive) {
      setCurrentPosition(simPosition);
    }
  }, [simPosition, tripActive, setCurrentPosition]);
  useEffect(() => {
    if (!route?.route_id && activeWeatherLayer === "route-weather") {
      setActiveWeatherLayer(null);
    }
  }, [route?.route_id, activeWeatherLayer]);
  // ── Persist session when route changes ─────────────────────
  useEffect(() => {
    if (route && origin && destination) {
      saveSession({ origin, destination, originText, destText, route });
    }
  }, [route, origin, destination, originText, destText]);

  const initialPoint = useMemo(
    () =>
      mapIncidentPointsMock[0] ?? {
        latitude: DEFAULT_CENTER[1],
        longitude: DEFAULT_CENTER[0],
        label: "Default",
      },
    [],
  );

  const fetchHazards = useCallback(async () => {
    try {
      const zones = await getActiveHazards();
      setHazardZones(zones);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    console.log("Fetching hazards on mount and every 10 minutes...");
    fetchHazards();
    const interval = setInterval(fetchHazards, 600_000);
    return () => clearInterval(interval);
  }, [fetchHazards]);

  // ── Map init ──────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !MAPBOX_PUBLIC_TOKEN) return;

    setMapError(null);
    try {
      mapboxgl.accessToken = MAPBOX_PUBLIC_TOKEN;

      const map = new mapboxgl.Map({
        container,
        style: isDark
          ? "mapbox://styles/mapbox/dark-v11"
          : "mapbox://styles/mapbox/streets-v12",
        center: [initialPoint.longitude, initialPoint.latitude],
        zoom: 11,
      });

      map.addControl(new mapboxgl.NavigationControl(), "top-right");
      map.addControl(
        new mapboxgl.GeolocateControl({
          positionOptions: { enableHighAccuracy: true },
          trackUserLocation: true,
        }),
        "top-right",
      );

      map.on("load", () => {
        map.addSource(ROUTE_SOURCE, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: ROUTE_LAYER,
          type: "line",
          source: ROUTE_SOURCE,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": "#3b82f6",
            "line-width": 5,
            "line-opacity": 0.85,
            "line-opacity-transition": { duration: 200, delay: 0 },
          },
        });

        map.addSource(HAZARD_SOURCE, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: HAZARD_FILL_LAYER,
          type: "fill",
          source: HAZARD_SOURCE,
          paint: { "fill-color": "#ef4444", "fill-opacity": 0.25 },
        });
        map.addLayer({
          id: HAZARD_OUTLINE_LAYER,
          type: "line",
          source: HAZARD_SOURCE,
          paint: {
            "line-color": "#ef4444",
            "line-width": 2,
            "line-dasharray": [2, 2],
          },
        });

        // ── Weather alert zones (amber/orange, distinct from red hazards) ──
        map.addSource(WEATHER_ALERT_SOURCE, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: WEATHER_ALERT_FILL,
          type: "fill",
          source: WEATHER_ALERT_SOURCE,
          paint: { "fill-color": "#f59e0b", "fill-opacity": 0.18 },
          layout: { visibility: "none" },
        });
        map.addLayer({
          id: WEATHER_ALERT_OUTLINE,
          type: "line",
          source: WEATHER_ALERT_SOURCE,
          paint: {
            "line-color": "#f59e0b",
            "line-width": 1.5,
            "line-dasharray": [3, 2],
          },
          layout: { visibility: "none" },
        });

        // ── Wind particle layer (requires Mapbox GL JS v3+) ──
        // Note: raster-array sources only support raster-particle, not raster layers.
        // try {

        //   map.addLayer({
        //     id: WIND_LAYER,
        //     type: "raster-particle" as any,
        //     source: WIND_SOURCE,
        //     "source-layer": "10winds",
        //     paint: {
        //       "raster-particle-speed-factor": 0.25,
        //       "raster-particle-fade-opacity-factor": 0.92,
        //       "raster-particle-reset-rate-factor": 0.35,
        //       "raster-particle-count": 12000,
        //       "raster-particle-max-speed": 90,
        //       "raster-particle-color": [
        //         "interpolate",
        //         ["linear"],
        //         ["raster-particle-speed"],
        //         0,
        //         "#25305a",
        //         10,
        //         "#2b5fb8",
        //         25,
        //         "#22b8c8",
        //         40,
        //         "#3fda7d",
        //         60,
        //         "#d9eb4b",
        //         90,
        //         "#fff7a3",
        //       ],
        //     } as any,
        //     layout: { visibility: "visible" },
        //   } as any);
        // } catch {
        //   // raster-particle/raster-array require Mapbox GL JS v3+
        // }

        // Click handler for weather alert popups
        map.on("click", WEATHER_ALERT_FILL, (e) => {
          if (!e.features?.length) return;
          const props = e.features[0].properties ?? {};
          new mapboxgl.Popup({ offset: 12, maxWidth: "260px" })
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font-family:system-ui;font-size:13px;">` +
                `<strong>${props.event || "Weather Alert"}</strong><br/>` +
                `<span style="text-transform:capitalize;">Severity: ${props.severity || "unknown"}</span><br/>` +
                `<span style="color:#666;">${props.region || ""}</span></div>`,
            )
            .addTo(map);
        });
        map.on("mouseenter", WEATHER_ALERT_FILL, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", WEATHER_ALERT_FILL, () => {
          map.getCanvas().style.cursor = "";
        });

        setMapIsLoaded(true);
      });

      const markers: mapboxgl.Marker[] = [];
      mapIncidentPointsMock.forEach((point) => {
        const marker = new mapboxgl.Marker({ color: "#dc2626" }).setLngLat([
          point.longitude,
          point.latitude,
        ]);
        const popup = new mapboxgl.Popup({ offset: 24 }).setHTML(
          `<strong>${point.label}</strong><br/>Urgency: ${point.urgency}`,
        );
        marker.setPopup(popup).addTo(map);
        markers.push(marker);
      });
      markersRef.current = markers;

      map.on("click", (e) => {
        const coord: Coordinate = { lng: e.lngLat.lng, lat: e.lngLat.lat };
        const label = formatCoord(coord);
        window.dispatchEvent(
          new CustomEvent("map-click", { detail: { coord, label } }),
        );
      });

      mapRef.current = map;

      return () => {
        markers.forEach((m) => m.remove());
        map.remove();
        mapRef.current = null;
        setMapIsLoaded(false);
      };
    } catch (err) {
      console.error("Map init failed:", err);
      setMapError(err instanceof Error ? err.message : "Map failed to load");
    }
  }, [initialPoint.latitude, initialPoint.longitude, isDark]);

  // ── Map click listener ────────────────────────────────────
  useEffect(() => {
    function handleMapClick(e: Event) {
      const { coord, label } = (e as CustomEvent).detail;
      if (mapClickMode === "origin") {
        setOrigin(coord);
        setOriginText(label);
        setMapClickMode(null);
      } else if (mapClickMode === "destination") {
        setDestination(coord);
        setDestText(label);
        setMapClickMode(null);
      }
    }
    window.addEventListener("map-click", handleMapClick);
    return () => window.removeEventListener("map-click", handleMapClick);
  }, [mapClickMode]);

  // ── Update route line ─────────────────────────────────────
  const prevRouteIdRef = useRef<string | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(ROUTE_SOURCE) as
      | mapboxgl.GeoJSONSource
      | undefined;
    if (!source) return;

    if (route?.geometry) {
      const routeChanged =
        prevRouteIdRef.current !== null &&
        prevRouteIdRef.current !== route.route_id;
      prevRouteIdRef.current = route.route_id;

      if (tripActive && routeChanged && map.getLayer(ROUTE_LAYER)) {
        // Fade out, swap data, fade back in
        map.setPaintProperty(ROUTE_LAYER, "line-opacity", 0);
        setTimeout(() => {
          source.setData({
            type: "Feature",
            properties: {},
            geometry: route.geometry,
          });
          map.setPaintProperty(ROUTE_LAYER, "line-opacity", 0.85);
        }, 200);
      } else {
        source.setData({
          type: "Feature",
          properties: {},
          geometry: route.geometry,
        });
      }

      if (!tripActive) {
        const coords = (route.geometry as GeoJSONLineString).coordinates as [
          number,
          number,
        ][];
        if (coords.length > 1) {
          const bounds = coords.reduce(
            (b, c) => b.extend(c as mapboxgl.LngLatLike),
            new mapboxgl.LngLatBounds(coords[0], coords[0]),
          );
          map.fitBounds(bounds, { padding: 80, duration: 800 });
        }
      }
    } else {
      prevRouteIdRef.current = null;
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }, [route, tripActive]);

  // ── Update origin/dest markers ────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    originMarkerRef.current?.remove();
    destMarkerRef.current?.remove();

    if (origin) {
      originMarkerRef.current = new mapboxgl.Marker({ color: "#22c55e" })
        .setLngLat([origin.lng, origin.lat])
        .setPopup(new mapboxgl.Popup({ offset: 24 }).setText("Origin"))
        .addTo(map);
    }
    if (destination) {
      destMarkerRef.current = new mapboxgl.Marker({ color: "#8b5cf6" })
        .setLngLat([destination.lng, destination.lat])
        .setPopup(new mapboxgl.Popup({ offset: 24 }).setText("Destination"))
        .addTo(map);
    }
  }, [origin, destination]);

  // ── Update current position marker (car icon) ───────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (currentPosition && tripActive) {
      ensureCarMarkerCSS();
      if (!positionMarkerRef.current) {
        const el = createCarMarkerElement();
        positionMarkerRef.current = new mapboxgl.Marker({
          element: el,
          anchor: "center",
        })
          .setLngLat([currentPosition.lng, currentPosition.lat])
          .addTo(map);
      } else {
        positionMarkerRef.current.setLngLat([
          currentPosition.lng,
          currentPosition.lat,
        ]);
        // No rotation — car keeps its default orientation
      }
    } else {
      positionMarkerRef.current?.remove();
      positionMarkerRef.current = null;
    }
  }, [currentPosition, tripActive, simBearing]);

  // ── Follow-camera: nav-mode tracking during active trip ────
  const prevTripActiveRef = useRef(false);
  const lastCameraUpdateRef = useRef(0);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (tripActive && currentPosition && followCamera) {
      const now = Date.now();
      if (now - lastCameraUpdateRef.current >= 300) {
        lastCameraUpdateRef.current = now;
        map.easeTo({
          center: [currentPosition.lng, currentPosition.lat],
          bearing: simBearing,
          pitch: 60,
          zoom: 15.5,
          duration: 350,
          easing: (t) => t,
        });
      }
    }

    // When trip ends, reset to overhead view showing the full route
    if (!tripActive && prevTripActiveRef.current) {
      map.easeTo({ pitch: 0, bearing: 0, duration: 600 });
      if (route?.geometry) {
        const coords = route.geometry.coordinates as [number, number][];
        if (coords.length > 1) {
          setTimeout(() => {
            const bounds = coords.reduce(
              (b, c) => b.extend(c as mapboxgl.LngLatLike),
              new mapboxgl.LngLatBounds(coords[0], coords[0]),
            );
            map.fitBounds(bounds, { padding: 80, duration: 800 });
          }, 650);
        }
      }
    }

    prevTripActiveRef.current = tripActive;
  }, [currentPosition, tripActive, simBearing, followCamera, route]);

  // Detect manual map interaction to pause follow-camera
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const pauseFollow = () => {
      if (tripActive) setFollowCamera(false);
    };
    map.on("dragstart", pauseFollow);
    return () => {
      map.off("dragstart", pauseFollow);
    };
  }, [tripActive]);

  // ── Update hazard polygons ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(HAZARD_SOURCE) as
      | mapboxgl.GeoJSONSource
      | undefined;
    if (!source) return;

    const features = hazardZones.map((hz) => ({
      type: "Feature" as const,
      properties: {
        hazard_id: hz.hazard_id,
        hazard_type: hz.hazard_type,
        severity: hz.severity,
      },
      geometry: hz.polygon,
    }));
    source.setData({ type: "FeatureCollection", features });
  }, [hazardZones]);

  // ── Rerouting: pulse route line ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(ROUTE_LAYER)) return;

    if (rerouting) {
      map.setPaintProperty(ROUTE_LAYER, "line-color", "#f59e0b");
      map.setPaintProperty(ROUTE_LAYER, "line-dasharray", [2, 2]);
    } else {
      map.setPaintProperty(ROUTE_LAYER, "line-color", "#3b82f6");
      map.setPaintProperty(ROUTE_LAYER, "line-dasharray", undefined);
    }
  }, [rerouting]);

  // ── Weather: toggle wind particle layer visibility ──────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(WIND_LAYER)) return;
    map.setLayoutProperty(
      WIND_LAYER,
      "visibility",
      showWind ? "visible" : "none",
    );
  }, [showWind]);

  // ── Weather: toggle alert zones visibility + fetch data ────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapIsLoaded) return;
    if (map.getLayer(WEATHER_ALERT_FILL)) {
      map.setLayoutProperty(
        WEATHER_ALERT_FILL,
        "visibility",
        showWeatherAlerts ? "visible" : "none",
      );
    }
    if (map.getLayer(WEATHER_ALERT_OUTLINE)) {
      map.setLayoutProperty(
        WEATHER_ALERT_OUTLINE,
        "visibility",
        showWeatherAlerts ? "visible" : "none",
      );
    }
    if (showWeatherAlerts) {
      const source = map.getSource(WEATHER_ALERT_SOURCE) as
        | mapboxgl.GeoJSONSource
        | undefined;
      if (weatherZones) {
        source?.setData(weatherZones as any);
      } else {
        fetchWeatherZones()
          .then((fc) => {
            const filtered = {
              ...fc,
              features: fc.features.filter((f) => f.geometry),
            };
            source?.setData(filtered as any);
          })
          .catch(() => {});
      }
    }
  }, [showWeatherAlerts, weatherZones, mapIsLoaded]);

  // ── Weather: live-update alert zones when demo steps ───────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapIsLoaded || !showWeatherAlerts || !weatherZones) return;
    const source = map.getSource(WEATHER_ALERT_SOURCE) as
      | mapboxgl.GeoJSONSource
      | undefined;
    source?.setData(weatherZones as any);
  }, [weatherZones, showWeatherAlerts, mapIsLoaded]);

  // ── Weather: fetch route weather when route changes ────────
  useEffect(() => {
    if (!route?.route_id || !showRouteWeather) {
      setRouteWeatherPoints([]);
      return;
    }
    fetchRouteWeather(route.route_id)
      .then(setRouteWeatherPoints)
      .catch(() => setRouteWeatherPoints([]));
  }, [route?.route_id, showRouteWeather]);

  // ── Weather: render route weather markers ──────────────────
  useEffect(() => {
    const map = mapRef.current;
    weatherMarkersRef.current.forEach((m) => m.remove());
    weatherMarkersRef.current = [];

    if (!map || !showRouteWeather || routeWeatherPoints.length === 0) return;

    for (const pt of routeWeatherPoints) {
      const temp =
        pt.temperature_c != null ? `${Math.round(pt.temperature_c)}°C` : "";
      const wind =
        pt.wind_speed_kmh != null
          ? `${Math.round(pt.wind_speed_kmh)} km/h`
          : "";
      const precip =
        pt.precipitation_probability != null && pt.precipitation_probability > 0
          ? `${pt.precipitation_probability}%`
          : "";

      const parts = [temp, wind, precip].filter(Boolean);
      if (parts.length === 0) continue;

      const el = document.createElement("div");
      el.style.cssText =
        "background:rgba(30,41,59,0.88);color:#f1f5f9;font-size:11px;font-family:system-ui;" +
        "padding:3px 7px;border-radius:10px;white-space:nowrap;pointer-events:none;" +
        "border:1px solid rgba(148,163,184,0.3);line-height:1.3;";
      el.innerHTML = parts.join(" &middot; ");

      const marker = new mapboxgl.Marker({ element: el, anchor: "bottom" })
        .setLngLat([pt.lng, pt.lat])
        .setOffset([0, -8])
        .addTo(map);
      weatherMarkersRef.current.push(marker);
    }

    return () => {
      weatherMarkersRef.current.forEach((m) => m.remove());
      weatherMarkersRef.current = [];
    };
  }, [routeWeatherPoints, showRouteWeather]);

  // ── Handlers ──────────────────────────────────────────────
  const handlePlanRoute = () => {
    const o = coordFromText(originText);
    const d = coordFromText(destText);
    if (o) setOrigin(o);
    if (d) setDestination(d);
    if (!o && !origin) return;
    if (!d && !destination) return;
    refetch();
  };

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const coord: Coordinate = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
        };
        setOrigin(coord);
        setOriginText(formatCoord(coord));
      },
      () => {},
    );
  };

  const handleStartTrip = () => {
    setFollowCamera(true);
    startTrip();
  };

  const handleEndTrip = () => {
    endTrip();
    clearSession();
  };

  const fitMapToRoute = useCallback((r: RouteResponse) => {
    const map = mapRef.current;
    if (!map || !r.geometry) return;
    const coords = r.geometry.coordinates as [number, number][];
    if (coords.length < 2) return;
    const bounds = coords.reduce(
      (b, c) => b.extend(c as mapboxgl.LngLatLike),
      new mapboxgl.LngLatBounds(coords[0], coords[0]),
    );
    map.fitBounds(bounds, { padding: 80, duration: 1000 });
  }, []);

  const handleRunDemo = useCallback(async () => {
    if (demoRunning || tripActive) return;
    setDemoRunning(true);
    const controls: DemoControls = {
      setOriginText,
      setDestText,
      setOrigin,
      setDestination,
      startTrip: () => {
        setFollowCamera(true);
        startTrip();
      },
      endTrip,
      refetch,
      setRouteDirectly,
      setRerouting,
      pauseSimulation,
      fetchHazards,
      setDemoStatus,
      fitMapToRoute,
      getCurrentPosition: () => currentPositionRef.current,
    };
    await runDemo(controls);
    setDemoRunning(false);
  }, [
    demoRunning,
    tripActive,
    startTrip,
    endTrip,
    refetch,
    setRouteDirectly,
    setRerouting,
    pauseSimulation,
    fetchHazards,
    fitMapToRoute,
  ]);

  // Auto-trigger demo from ?demo URL parameter
  const demoTriggeredRef = useRef(false);
  useEffect(() => {
    if (demoTriggeredRef.current) return;
    const params = new URLSearchParams(window.location.search);
    if (params.has("demo")) {
      demoTriggeredRef.current = true;
      // Small delay to let the map initialize
      const timeout = setTimeout(() => handleRunDemo(), 2000);
      return () => clearTimeout(timeout);
    }
  }, [handleRunDemo]);

  const mapCenter: Coordinate | null =
    currentPosition ?? origin ?? destination ?? null;
  const inputsDisabled = tripActive || demoRunning;

  return (
    <View className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      {/* ── Rerouting banner ────────────────────────────── */}
      {rerouting && (
        <View className="z-10 bg-amber-500 px-4 py-2">
          <Text className="text-center text-sm font-semibold text-black">
            {tripActive
              ? "⚠ Rerouting from your current position..."
              : "⚠ Rerouting — new hazard detected on your path…"}
          </Text>
        </View>
      )}

      {/* ── Demo status banner ──────────────────────────── */}
      {demoStatus !== "" && (
        <View
          className={`z-10 px-4 py-2 ${isDark ? "bg-indigo-900" : "bg-indigo-100"}`}
        >
          <Text
            className={`text-center text-sm font-medium ${isDark ? "text-indigo-200" : "text-indigo-800"}`}
          >
            {demoStatus}
          </Text>
        </View>
      )}

      <View className="flex-1 flex-row">
        {/* ── Sidebar panel ─────────────────────────────── */}
        <View
          className={`w-80 border-r p-4 ${isDark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-white"}`}
          // @ts-expect-error web-only overflow style
          style={{ minWidth: 320, overflowY: "auto" }}
        >
          <Text
            className={`mb-3 text-lg font-bold ${isDark ? "text-white" : "text-slate-900"}`}
          >
            Route Planner
          </Text>

          {/* Origin */}
          <Text
            className={`mb-1 text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}
          >
            Origin (lat, lng)
          </Text>
          <View className="mb-2 flex-row items-center gap-2">
            <TextInput
              className={`flex-1 rounded-lg px-3 py-2 text-sm ${
                isDark
                  ? "bg-slate-800 text-white"
                  : "bg-slate-100 text-slate-900"
              } ${mapClickMode === "origin" ? "border-2 border-green-500" : ""}`}
              placeholder="43.706, -79.41"
              placeholderTextColor={isDark ? "#64748b" : "#94a3b8"}
              value={originText}
              onChangeText={setOriginText}
              editable={!inputsDisabled}
            />
            <Pressable
              onPress={() =>
                setMapClickMode(mapClickMode === "origin" ? null : "origin")
              }
              disabled={inputsDisabled}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "origin"
                  ? "bg-green-600"
                  : isDark
                    ? "bg-slate-700"
                    : "bg-slate-200"
              }`}
            >
              <Text
                className={`text-xs ${mapClickMode === "origin" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}
              >
                📍
              </Text>
            </Pressable>
          </View>
          {!inputsDisabled && (
            <Pressable onPress={handleUseCurrentLocation} className="mb-3">
              <Text className="text-xs text-blue-500">
                Use current location
              </Text>
            </Pressable>
          )}

          {/* Destination */}
          <Text
            className={`mb-1 text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}
          >
            Destination (lat, lng)
          </Text>
          <View className="mb-3 flex-row items-center gap-2">
            <TextInput
              className={`flex-1 rounded-lg px-3 py-2 text-sm ${
                isDark
                  ? "bg-slate-800 text-white"
                  : "bg-slate-100 text-slate-900"
              } ${mapClickMode === "destination" ? "border-2 border-purple-500" : ""}`}
              placeholder="43.65, -79.38"
              placeholderTextColor={isDark ? "#64748b" : "#94a3b8"}
              value={destText}
              onChangeText={setDestText}
              editable={!inputsDisabled}
            />
            <Pressable
              onPress={() =>
                setMapClickMode(
                  mapClickMode === "destination" ? null : "destination",
                )
              }
              disabled={inputsDisabled}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "destination"
                  ? "bg-purple-600"
                  : isDark
                    ? "bg-slate-700"
                    : "bg-slate-200"
              }`}
            >
              <Text
                className={`text-xs ${mapClickMode === "destination" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}
              >
                🏁
              </Text>
            </Pressable>
          </View>

          {mapClickMode && (
            <Text className="mb-2 text-xs text-amber-500">
              Click the map to set {mapClickMode}
            </Text>
          )}

          {/* Plan Route button */}
          {!tripActive && (
            <Pressable
              onPress={handlePlanRoute}
              disabled={loading || inputsDisabled}
              className={`mb-4 rounded-lg py-3 ${loading || inputsDisabled ? "bg-blue-400" : "bg-blue-600"}`}
            >
              <Text className="text-center text-sm font-semibold text-white">
                {loading ? "Planning…" : "Plan Route"}
              </Text>
            </Pressable>
          )}

          {/* Error */}
          {error && (
            <View className="mb-3 rounded-lg bg-red-900/30 p-3">
              <Text className="text-xs text-red-400">{error}</Text>
            </View>
          )}

          {/* Route info */}
          {route && (
            <View
              className={`mb-4 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}
            >
              <Text
                className={`mb-1 text-sm font-semibold ${isDark ? "text-white" : "text-slate-900"}`}
              >
                Route Details
              </Text>
              <Text
                className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
              >
                Distance: {formatDistance(route.distance_meters)}
              </Text>
              <Text
                className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
              >
                Duration: {formatDuration(route.duration_seconds)}
              </Text>
              {route.hazards_avoided.length > 0 && (
                <Text className="mt-1 text-xs text-amber-400">
                  Hazards avoided: {route.hazards_avoided.length}
                </Text>
              )}
              {route.instructions.length > 0 && (
                <View className="mt-2">
                  <Text
                    className={`mb-1 text-xs font-medium ${isDark ? "text-slate-300" : "text-slate-600"}`}
                  >
                    Directions
                  </Text>
                  {route.instructions.slice(0, 6).map((instr, i) => (
                    <Text
                      key={i}
                      className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
                    >
                      {i + 1}. {instr}
                    </Text>
                  ))}
                  {route.instructions.length > 6 && (
                    <Text
                      className={`text-xs ${isDark ? "text-slate-500" : "text-slate-400"}`}
                    >
                      +{route.instructions.length - 6} more…
                    </Text>
                  )}
                </View>
              )}
            </View>
          )}

          {/* ── Trip controls ──────────────────────────── */}
          {route && !tripActive && !demoRunning && (
            <Pressable
              onPress={handleStartTrip}
              className="mb-4 rounded-lg bg-green-600 py-3"
            >
              <Text className="text-center text-sm font-semibold text-white">
                Start Trip
              </Text>
            </Pressable>
          )}

          {tripActive && (
            <View
              className={`mb-4 rounded-xl p-3 ${isDark ? "bg-green-950/40" : "bg-green-50"}`}
            >
              <View className="mb-2 flex-row items-center gap-2">
                <View className="h-2 w-2 rounded-full bg-green-500" />
                <Text
                  className={`text-xs font-semibold ${isDark ? "text-green-400" : "text-green-700"}`}
                >
                  Trip in Progress
                </Text>
              </View>

              {currentPosition && (
                <Text
                  className={`mb-1 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
                >
                  Position: {formatCoord(currentPosition)}
                </Text>
              )}

              {/* Progress bar */}
              <View
                className={`mb-2 h-2 overflow-hidden rounded-full ${isDark ? "bg-slate-700" : "bg-slate-200"}`}
              >
                <View
                  className="h-full rounded-full bg-green-500"
                  style={{ width: `${Math.round(simProgress * 100)}%` }}
                />
              </View>
              <Text
                className={`mb-3 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
              >
                {Math.round(simProgress * 100)}% complete
              </Text>

              <View className="flex-row gap-2">
                {!followCamera && (
                  <Pressable
                    onPress={() => setFollowCamera(true)}
                    className="flex-1 rounded-lg bg-blue-600 py-2"
                  >
                    <Text className="text-center text-sm font-semibold text-white">
                      Re-center
                    </Text>
                  </Pressable>
                )}
                <Pressable
                  onPress={handleEndTrip}
                  disabled={demoRunning}
                  className="flex-1 rounded-lg bg-red-600 py-2"
                >
                  <Text className="text-center text-sm font-semibold text-white">
                    End Trip
                  </Text>
                </Pressable>
              </View>
            </View>
          )}

          {/* Hazard zones count */}
          {hazardZones.length > 0 && (
            <View
              className={`mb-3 rounded-xl p-3 ${isDark ? "bg-red-950/40" : "bg-red-50"}`}
            >
              <Text
                className={`text-xs font-medium ${isDark ? "text-red-400" : "text-red-600"}`}
              >
                {hazardZones.length} active hazard zone
                {hazardZones.length > 1 ? "s" : ""}
              </Text>
            </View>
          )}

          {/* Report Hazard */}
          <Pressable
            onPress={() => setHazardModalVisible(true)}
            className={`mb-4 rounded-lg py-3 ${isDark ? "bg-red-700" : "bg-red-600"}`}
          >
            <Text className="text-center text-sm font-semibold text-white">
              Report Hazard
            </Text>
          </Pressable>

          {/* Subtle demo trigger */}
          {!demoRunning && !tripActive && (
            <Pressable onPress={handleRunDemo} className="mt-2 py-2">
              <Text
                className={`text-center text-xs ${isDark ? "text-slate-600" : "text-slate-400"}`}
              >
                Try demo scenario
              </Text>
            </Pressable>
          )}
          {demoRunning && (
            <Text
              className={`mt-2 text-center text-xs ${isDark ? "text-slate-500" : "text-slate-400"}`}
            >
              Demo in progress...
            </Text>
          )}
        </View>

        {/* ── Map container ─────────────────────────────── */}
        <View
          className="flex-1"
          style={{ minHeight: 400, position: "relative" as any }}
        >
          {/* Weather layer overlay (includes live alert signal heatmaps) */}
          {MAPBOX_PUBLIC_TOKEN && !mapError && (
            <WeatherLayerOverlay
              map={mapRef.current}
              mapLoaded={mapIsLoaded}
              showWeatherAlerts={showWeatherAlerts}
              showWind={showWind}
              onToggleAlerts={(on) => setActiveWeatherLayer(on ? "alerts" : null)}
              onToggleWind={(on) => setActiveWeatherLayer(on ? "wind" : null)}
              theme={theme}
            />
          )}
          {mapError ? (
            <View
              className={`flex-1 items-center justify-center px-4 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}
            >
              <Text
                className={`mb-2 text-center text-sm font-medium ${isDark ? "text-red-400" : "text-red-600"}`}
              >
                Map failed to load
              </Text>
              <Text
                className={`text-center text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}
              >
                {mapError}
              </Text>
            </View>
          ) : MAPBOX_PUBLIC_TOKEN ? (
            <div
              ref={containerRef}
              style={{
                width: "100%",
                height: "100%",
                minHeight: 400,
                cursor: mapClickMode ? "crosshair" : undefined,
              }}
            />
          ) : (
            <View
              className={`flex-1 items-center justify-center px-4 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}
            >
              <Text
                className={`text-center text-sm ${isDark ? "text-slate-300" : "text-slate-600"}`}
              >
                Mapbox token not set. Add EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN in
                frontend/.env.
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* ── Report Hazard Modal ──────────────────────── */}
      <ReportHazardModal
        visible={hazardModalVisible}
        onClose={() => {
          setHazardModalVisible(false);
          fetchHazards();
        }}
        currentLocation={mapCenter}
      />
    </View>
  );
}
