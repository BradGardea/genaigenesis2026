import { useCallback, useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Pressable, Text, TextInput, View } from "react-native";
import { AppTheme } from "../types/theme";
import { Coordinate, GeoJSONLineString, HazardZone, RouteResponse, RouteWeatherPoint } from "../types/domain";
import { useEvacuationRoute } from "../hooks/useEvacuationRoute";
import { useTripSimulation, buildCumulativeDistances } from "../hooks/useTripSimulation";
import {
  deactivateHazard,
  getActiveHazards,
  fetchWeatherZones,
  fetchRouteWeather,
  reportHazard,
} from "../services/api";
import { ReportHazardModal } from "../components/ReportHazardModal";
import {
  WeatherLayerOverlay,
  WeatherLayerMode,
} from "../components/WeatherLayerOverlay";
import { AlertSignalsLayer } from "../components/AlertSignalsLayer";
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
const CITY_STATE_SOURCE = "city-state-impacts";
const CITY_STATE_LAYER = "city-state-impacts-heatmap";
const CITY_STATE_LABEL_LAYER = "city-state-impacts-label";

const DEFAULT_CENTER: [number, number] = [35.321269, -21.992207];
const DEFAULT_ROUTE_ORIGIN: Coordinate = { lat: -21.992207, lng: 35.321269 };
const DEFAULT_ROUTE_DESTINATION: Coordinate = { lat: -22.005956, lng: 35.285656 };
const PROTECTED_SEED_STEPS = 30;

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

function formatLatLon6(lat: number, lon: number): string {
  return `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
}

interface CityStateArea {
  lat: number;
  lon: number;
  impact_type: string;
  severity: number;
  danger_to_remain: string;
  status: string;
  radius_m: number;
  node_id?: string;
  source_kind?: string;
  source_refs?: string[];
}

function toHazardType(impactType: string, severity: number): string | null {
  if (impactType === "road_closure") return "roadblock";
  if (impactType === "flooding") return "flood";
  if (impactType === "high_wind" && severity >= 82) return "wind";
  if (impactType === "structure_damage" && severity >= 88) return "roadblock";
  return null;
}

function toImpactIcon(impactType: string): string {
  if (impactType === "rain") return "N";
  if (impactType === "high_wind") return "W";
  if (impactType === "flooding") return "F";
  if (impactType === "road_closure") return "R";
  if (impactType === "powerline_failure") return "P";
  if (impactType === "structure_damage") return "S";
  if (impactType === "debris") return "D";
  return "!";
}

function extractCityStateAreas(raw: Record<string, unknown> | undefined): CityStateArea[] {
  if (!raw) return [];
  const cityState = raw.city_state;
  if (!cityState || typeof cityState !== "object") return [];
  const areas = (cityState as { affected_areas?: unknown }).affected_areas;
  if (!Array.isArray(areas)) return [];

  return areas
    .filter((item): item is CityStateArea => {
      if (!item || typeof item !== "object") return false;
      const value = item as Partial<CityStateArea>;
      return (
        typeof value.lat === "number" &&
        typeof value.lon === "number" &&
        typeof value.impact_type === "string" &&
        typeof value.severity === "number" &&
        typeof value.danger_to_remain === "string" &&
        typeof value.status === "string" &&
        typeof value.radius_m === "number" &&
        (value.node_id == null || typeof value.node_id === "string") &&
        (value.source_kind == null || typeof value.source_kind === "string") &&
        (value.source_refs == null || Array.isArray(value.source_refs))
      );
    })
    .slice(0, 200);
}

function isHighDanger(area: CityStateArea): boolean {
  return (
    area.impact_type === "road_closure" ||
    area.danger_to_remain === "high" ||
    area.danger_to_remain === "extreme"
  );
}

function isProtectedCoastalSeed(area: CityStateArea, stepIndex: number): boolean {
  return stepIndex <= PROTECTED_SEED_STEPS && (area.source_kind?.endsWith("_protected") ?? false);
}

function approxDistanceMeters(a: CityStateArea, b: CityStateArea): number {
  const dy = (a.lat - b.lat) * 111_320;
  const dx = (a.lon - b.lon) * 111_320 * Math.cos(((a.lat + b.lat) / 2) * Math.PI / 180);
  return Math.hypot(dx, dy);
}

function compressIntoHighDangerZones(areas: CityStateArea[], stepIndex: number): CityStateArea[] {
  const cloned = areas.map((a) => ({ ...a }));
  const absorbed = new Set<number>();

  for (let i = 0; i < cloned.length; i++) {
    const high = cloned[i];
    if (isProtectedCoastalSeed(high, stepIndex)) continue;
    if (!isHighDanger(high)) continue;
    let mergedCount = 0;
    const mergedIndices: number[] = [];

    for (let j = 0; j < cloned.length; j++) {
      if (i === j || absorbed.has(j)) continue;
      const low = cloned[j];
      if (isProtectedCoastalSeed(low, stepIndex)) continue;
      if (high.impact_type !== low.impact_type) continue;
      if (isHighDanger(low)) continue;
      if (approxDistanceMeters(high, low) > high.radius_m) continue;

      absorbed.add(j);
      mergedIndices.push(j);
      mergedCount += 1;
    }

    if (mergedCount > 0) {
      high.radius_m = Math.min(2500, Math.round(high.radius_m + Math.sqrt(mergedCount) * 80));
      high.severity = Math.min(100, high.severity + Math.min(mergedCount, 8));
      high.danger_to_remain = "high";
      high.status = "merged_cluster";
      const refs = new Set<string>(high.source_refs ?? []);
      refs.add(high.node_id ?? "");
      for (const idx of mergedIndices) {
        const low = cloned[idx];
        (low.source_refs ?? []).forEach((r) => refs.add(r));
        if (low.node_id) refs.add(low.node_id);
      }
      high.source_kind = "high_danger_absorb";
      high.source_refs = Array.from(refs).filter(Boolean).slice(0, 20);
    }
  }

  return cloned.filter((_, idx) => !absorbed.has(idx));
}

function collapseNearbyDisplayNodes(areas: CityStateArea[], stepIndex: number, mergeDistanceM = 230): CityStateArea[] {
  const protectedSeeds = areas.filter((a) => isProtectedCoastalSeed(a, stepIndex)).map((a) => ({ ...a }));
  const mergeCandidates = areas.filter((a) => !isProtectedCoastalSeed(a, stepIndex));
  const grouped = new Map<string, CityStateArea[]>();
  for (const area of mergeCandidates) {
    const bucket = isHighDanger(area) ? "high" : "low";
    const key = `${area.impact_type}:${bucket}`;
    const list = grouped.get(key);
    if (list) list.push({ ...area });
    else grouped.set(key, [{ ...area }]);
  }

  const collapsed: CityStateArea[] = [];
  for (const [, group] of grouped) {
    const pending = [...group];
    while (pending.length > 0) {
      const seed = pending.pop()!;
      const cluster = [seed];
      let changed = true;
      while (changed) {
        changed = false;
        const keep: CityStateArea[] = [];
        for (const candidate of pending) {
          const near = cluster.some((c) => approxDistanceMeters(c, candidate) <= mergeDistanceM);
          if (near) {
            cluster.push(candidate);
            changed = true;
          } else {
            keep.push(candidate);
          }
        }
        pending.splice(0, pending.length, ...keep);
      }

      if (cluster.length === 1) {
        collapsed.push(cluster[0]);
        continue;
      }

      const totalWeight = cluster.reduce((sum, c) => sum + Math.max(c.radius_m, 1), 0);
      const lat = cluster.reduce((sum, c) => sum + c.lat * Math.max(c.radius_m, 1), 0) / totalWeight;
      const lon = cluster.reduce((sum, c) => sum + c.lon * Math.max(c.radius_m, 1), 0) / totalWeight;
      const severity = Math.min(100, Math.max(...cluster.map((c) => c.severity)) + Math.min(cluster.length, 6));
      const type = cluster[0].impact_type;
      const cap = type === "flooding" || type === "high_wind" || type === "rain" ? 1300 : 2200;
      const radius_m = Math.min(
        cap,
        Math.round(Math.max(...cluster.map((c) => c.radius_m)) + Math.sqrt(cluster.length) * 80)
      );
      const refs = new Set<string>();
      cluster.forEach((c) => {
        (c.source_refs ?? []).forEach((r) => refs.add(r));
        if (c.node_id) refs.add(c.node_id);
      });
      collapsed.push({
        lat,
        lon,
        impact_type: cluster[0].impact_type,
        severity,
        danger_to_remain: severity >= 70 ? "high" : cluster[0].danger_to_remain,
        status: "merged_cluster",
        radius_m,
        node_id: `display-merge-${cluster[0].impact_type}-${Math.round(lat * 1e6)}-${Math.round(lon * 1e6)}`,
        source_kind: "display_collapsed",
        source_refs: Array.from(refs).slice(0, 24),
      });
    }
  }
  return [...protectedSeeds, ...collapsed];
}

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
  const { currentStep, currentStepIndex, totalSteps, stepHistory } = useDisasterDemo();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const originMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const destMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const positionMarkerRef = useRef<mapboxgl.Marker | null>(null);

  const [originText, setOriginText] = useState("");
  const [destText, setDestText] = useState("");
  const [origin, setOrigin] = useState<Coordinate | null>(null);
  const [destination, setDestination] = useState<Coordinate | null>(null);
  const [hazardZones, setHazardZones] = useState<HazardZone[]>([]);
  const [hazardModalVisible, setHazardModalVisible] = useState(false);
  const [mapClickMode, setMapClickMode] = useState<"origin" | "destination" | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [plannerCollapsed, setPlannerCollapsed] = useState(false);
  const [mapReadyVersion, setMapReadyVersion] = useState(0);
  const [mapIsLoaded, setMapIsLoaded] = useState(false);

  // â”€â”€ Weather layer state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const [showWind, setShowWind] = useState(false);
  const [showWeatherAlerts, setShowWeatherAlerts] = useState(false);
  const [showRouteWeather, setShowRouteWeather] = useState(false);
  const [routeWeatherPoints, setRouteWeatherPoints] = useState<RouteWeatherPoint[]>([]);
  const weatherMarkersRef = useRef<mapboxgl.Marker[]>([]);

  const {
    route, loading, error, rerouting,
    tripActive, currentPosition,
    refetch, startTrip, endTrip, setCurrentPosition,
  } = useEvacuationRoute(origin, destination);

  const [followCamera, setFollowCamera] = useState(true);
  const routeRef = useRef<RouteResponse | null>(null);
  useEffect(() => {
    routeRef.current = route;
  }, [route]);

  // â”€â”€ Trip simulation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const {
    position: simPosition,
    bearing: simBearing,
    progress: simProgress,
  } = useTripSimulation(
    route?.geometry ?? null,
    route?.segment_durations,
    tripActive,
    20,
    rerouting
  );

  useEffect(() => {
    if (simPosition && tripActive) {
      setCurrentPosition(simPosition);
    }
  }, [simPosition, tripActive, setCurrentPosition]);
  useEffect(() => {
    if (origin || destination) {
      return;
    }
    const defaultOrigin = DEFAULT_ROUTE_ORIGIN;
    const defaultDestination = DEFAULT_ROUTE_DESTINATION;
    setOrigin(defaultOrigin);
    setDestination(defaultDestination);
    setOriginText(formatCoord(defaultOrigin));
    setDestText(formatCoord(defaultDestination));
  }, [origin, destination]);

  const fetchHazards = useCallback(async () => {
    try {
      const zones = await getActiveHazards();
      setHazardZones(zones);
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => {
    fetchHazards();
    const interval = setInterval(fetchHazards, 10_000);
    return () => clearInterval(interval);
  }, [fetchHazards]);

  // â”€â”€ Map init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !MAPBOX_PUBLIC_TOKEN) return;

    setMapError(null);
    try {
      mapboxgl.accessToken = MAPBOX_PUBLIC_TOKEN;

      const map = new mapboxgl.Map({
        container,
        style: isDark ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12",
        center: DEFAULT_CENTER,
        zoom: 11,
      });

      map.addControl(new mapboxgl.NavigationControl(), "top-right");
      map.addControl(
        new mapboxgl.GeolocateControl({
          positionOptions: { enableHighAccuracy: true },
          trackUserLocation: true,
        }),
        "top-right"
      );

      map.on("load", () => {
        setMapReadyVersion((value) => value + 1);
        setMapIsLoaded(true);
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
          paint: {
            "fill-color": [
              "match",
              ["get", "hazard_type"],
              "flood",
              "#2563eb",
              "wind",
              "#6b7280",
              "roadblock",
              "#ef4444",
              "#ef4444",
            ],
            "fill-opacity": 0.25,
          },
        });
        map.addLayer({
          id: HAZARD_OUTLINE_LAYER,
          type: "line",
          source: HAZARD_SOURCE,
          paint: {
            "line-color": [
              "match",
              ["get", "hazard_type"],
              "flood",
              "#2563eb",
              "wind",
              "#6b7280",
              "roadblock",
              "#ef4444",
              "#ef4444",
            ],
            "line-width": 2,
            "line-dasharray": [2, 2],
          },
        });

        map.addSource(CITY_STATE_SOURCE, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: CITY_STATE_LAYER,
          type: "heatmap",
          source: CITY_STATE_SOURCE,
          paint: {
            // Weight each point by its severity (0–100 → 0–1)
            "heatmap-weight": [
              "interpolate",
              ["linear"],
              ["get", "severity"],
              0, 0,
              100, 1,
            ],
            // Increase intensity at higher zoom levels
            "heatmap-intensity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              8, 0.6,
              14, 2,
            ],
            // Radius grows with zoom
            "heatmap-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              8, 18,
              14, 48,
            ],
            // Severity gradient: transparent → blue → cyan → green → yellow → orange → red
            "heatmap-color": [
              "interpolate",
              ["linear"],
              ["heatmap-density"],
              0,   "rgba(0,0,255,0)",
              0.15, "rgba(65,182,196,0.6)",
              0.35, "rgba(127,205,187,0.75)",
              0.55, "rgba(255,237,160,0.85)",
              0.75, "rgba(253,141,60,0.9)",
              1,   "rgba(215,25,28,1)",
            ],
            "heatmap-opacity": 0.85,
          },
        });
        map.addLayer({
          id: CITY_STATE_LABEL_LAYER,
          type: "symbol",
          source: CITY_STATE_SOURCE,
          layout: {
            "text-field": ["get", "icon"],
            "text-size": 12,
            "text-offset": [0, 0],
            "text-allow-overlap": true,
          },
        });
        map.on("click", CITY_STATE_LAYER, (e) => {
          if (!e.features?.length) return;
          const props = e.features[0].properties ?? {};
          const geom = e.features[0].geometry;
          const coords =
            geom && geom.type === "Point" && Array.isArray(geom.coordinates)
              ? (geom.coordinates as number[])
              : null;
          const impactType = String(props.impact_type ?? "unknown").replace("_", " ");
          const severity = props.severity ?? "unknown";
          const danger = props.danger_to_remain ?? "unknown";
          const status = props.status ?? "unknown";
          const radius = props.radius_m ?? "n/a";
          const sourceKind = props.source_kind ?? "unknown";
          const sourceRefsRaw = String(props.source_refs ?? "");
          const sourceRefs = sourceRefsRaw
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .slice(0, 6)
            .join(", ");
          const step = props.step_index != null ? Number(props.step_index) + 1 : "n/a";
          const latLon =
            coords && coords.length >= 2
              ? formatLatLon6(Number(coords[1]), Number(coords[0]))
              : "n/a";
          const popupHtml = [
            '<div style="font-family:system-ui;font-size:13px;line-height:1.4;">',
            "<strong>Incident: " + impactType + "</strong><br/>",
            "<span>Severity: " + severity + "</span><br/>",
            "<span>Danger: " + danger + "</span><br/>",
            "<span>Status: " + status + "</span><br/>",
            "<span>Radius: " + radius + " m</span><br/>",
            "<span>Lat,Lon: " + latLon + "</span><br/>",
            "<span>Source: " + sourceKind + "</span><br/>",
            "<span>Refs: " + (sourceRefs || "n/a") + "</span><br/>",
            '<span style="color:#64748b;">Step ' + step + "</span>",
            "</div>",
          ].join("");
          new mapboxgl.Popup({ offset: 12, maxWidth: "280px" })
            .setLngLat(e.lngLat)
            .setHTML(popupHtml)
            .addTo(map);
        });
        map.on("click", CITY_STATE_LABEL_LAYER, (e) => {
          if (!e.features?.length) return;
          const props = e.features[0].properties ?? {};
          const geom = e.features[0].geometry;
          const coords =
            geom && geom.type === "Point" && Array.isArray(geom.coordinates)
              ? (geom.coordinates as number[])
              : null;
          const impactType = String(props.impact_type ?? "unknown").replace("_", " ");
          const severity = props.severity ?? "unknown";
          const danger = props.danger_to_remain ?? "unknown";
          const status = props.status ?? "unknown";
          const radius = props.radius_m ?? "n/a";
          const sourceKind = props.source_kind ?? "unknown";
          const sourceRefsRaw = String(props.source_refs ?? "");
          const sourceRefs = sourceRefsRaw
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .slice(0, 6)
            .join(", ");
          const step = props.step_index != null ? Number(props.step_index) + 1 : "n/a";
          const latLon =
            coords && coords.length >= 2
              ? formatLatLon6(Number(coords[1]), Number(coords[0]))
              : "n/a";
          const popupHtml = [
            '<div style="font-family:system-ui;font-size:13px;line-height:1.4;">',
            "<strong>Incident: " + impactType + "</strong><br/>",
            "<span>Severity: " + severity + "</span><br/>",
            "<span>Danger: " + danger + "</span><br/>",
            "<span>Status: " + status + "</span><br/>",
            "<span>Radius: " + radius + " m</span><br/>",
            "<span>Lat,Lon: " + latLon + "</span><br/>",
            "<span>Source: " + sourceKind + "</span><br/>",
            "<span>Refs: " + (sourceRefs || "n/a") + "</span><br/>",
            '<span style="color:#64748b;">Step ' + step + "</span>",
            "</div>",
          ].join("");
          new mapboxgl.Popup({ offset: 12, maxWidth: "280px" })
            .setLngLat(e.lngLat)
            .setHTML(popupHtml)
            .addTo(map);
        });
        map.on("mouseenter", CITY_STATE_LAYER, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", CITY_STATE_LAYER, () => { map.getCanvas().style.cursor = ""; });
        map.on("mouseenter", CITY_STATE_LABEL_LAYER, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", CITY_STATE_LABEL_LAYER, () => { map.getCanvas().style.cursor = ""; });

        // â”€â”€ Weather alert zones (amber/orange, distinct from red hazards) â”€â”€
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
          paint: { "line-color": "#f59e0b", "line-width": 1.5, "line-dasharray": [3, 2] },
          layout: { visibility: "none" },
        });

        // â”€â”€ Wind particle layer (Mapbox native GFS wind data) â”€â”€
        map.addSource(WIND_SOURCE, {
          type: "raster-array" as any,
          url: "mapbox://rasterarrayexamples.gfs-winds",
          tileSize: 512,
        });
        map.addLayer({
          id: WIND_LAYER,
          type: "raster-particle" as any,
          source: WIND_SOURCE,
          "source-layer": "10winds",
          paint: {
            "raster-particle-speed-factor": 0.4,
            "raster-particle-fade-opacity-factor": 0.9,
            "raster-particle-reset-rate-factor": 0.4,
            "raster-particle-count": 4000,
            "raster-particle-max-speed": 40,
            "raster-particle-color": [
              "interpolate",
              ["linear"],
              ["raster-particle-speed"],
              1.5, "rgba(134,163,171,255)",
              4.12, "rgba(110,143,208,255)",
              6.17, "rgba(15,147,167,255)",
              9.26, "rgba(57,163,57,255)",
              11.83, "rgba(194,134,62,255)",
              14.92, "rgba(200,66,13,255)",
              18.0, "rgba(210,0,50,255)",
              21.6, "rgba(175,80,136,255)",
              25.21, "rgba(117,74,147,255)",
              29.32, "rgba(68,105,141,255)",
              33.44, "rgba(194,251,119,255)",
              43.72, "rgba(241,255,109,255)",
              50.41, "rgba(255,255,255,255)",
              59.16, "rgba(0,255,255,255)",
              69.44, "rgba(255,37,255,255)",
            ],
          } as any,
          layout: { visibility: "none" },
        } as any);

        // Click handler for weather alert popups
        map.on("click", WEATHER_ALERT_FILL, (e) => {
          if (!e.features?.length) return;
          const props = e.features[0].properties ?? {};
          const popupHtml =
            '<div style="font-family:system-ui;font-size:13px;">' +
            "<strong>" + (props.event || "Weather Alert") + "</strong><br/>" +
            '<span style="text-transform:capitalize;">Severity: ' +
            (props.severity || "unknown") +
            "</span><br/>" +
            '<span style="color:#666;">' +
            (props.region || "") +
            "</span></div>";
          new mapboxgl.Popup({ offset: 12, maxWidth: "260px" })
            .setLngLat(e.lngLat)
            .setHTML(popupHtml)
            .addTo(map);
        });
        map.on("mouseenter", WEATHER_ALERT_FILL, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", WEATHER_ALERT_FILL, () => { map.getCanvas().style.cursor = ""; });
      });

      map.on("click", (e) => {
        const coord: Coordinate = { lng: e.lngLat.lng, lat: e.lngLat.lat };
        const label = formatCoord(coord);
        window.dispatchEvent(new CustomEvent("map-click", { detail: { coord, label } }));
      });

      mapRef.current = map;

      return () => {
        map.remove();
        mapRef.current = null;
      };
    } catch (err) {
      console.error("Map init failed:", err);
      setMapError(err instanceof Error ? err.message : "Map failed to load");
    }
  }, [isDark]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const raf = requestAnimationFrame(() => {
      map.resize();
    });
    const timeout = setTimeout(() => {
      map.resize();
    }, 120);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timeout);
    };
  }, [plannerCollapsed]);

  // â”€â”€ Map click listener â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Update route line â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const prevRouteIdRef = useRef<string | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(ROUTE_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    if (route?.geometry) {
      const routeChanged = prevRouteIdRef.current !== null && prevRouteIdRef.current !== route.route_id;
      prevRouteIdRef.current = route.route_id;

      // Build display geometry — trim to show only the route ahead of the
      // user's current position (like Google Maps) during demo stepping.
      let displayGeometry = route.geometry;

      if (currentPosition && !tripActive) {
        const coords = route.geometry.coordinates as [number, number][];
        let bestIdx = 0;
        let bestDist = Infinity;
        for (let i = 0; i < coords.length; i++) {
          const [lng, lat] = coords[i];
          const d = Math.hypot(lng - currentPosition.lng, lat - currentPosition.lat);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }
        const trimmedCoords: [number, number][] = [
          [currentPosition.lng, currentPosition.lat],
          ...coords.slice(bestIdx + 1),
        ];
        if (trimmedCoords.length >= 2) {
          displayGeometry = {
            type: "LineString" as const,
            coordinates: trimmedCoords,
          };
        }
      }

      // Fade transition on reroute (active trip OR demo stepping)
      if ((tripActive || currentPosition) && routeChanged && map.getLayer(ROUTE_LAYER)) {
        map.setPaintProperty(ROUTE_LAYER, "line-opacity", 0);
        setTimeout(() => {
          source.setData({ type: "Feature", properties: {}, geometry: displayGeometry });
          map.setPaintProperty(ROUTE_LAYER, "line-opacity", 0.85);
        }, 200);
      } else {
        source.setData({ type: "Feature", properties: {}, geometry: displayGeometry });
      }

      // Only fit-bounds on initial load (no current position yet)
      if (!tripActive && !currentPosition) {
        const coords = (displayGeometry as GeoJSONLineString).coordinates as [number, number][];
        if (coords.length > 1) {
          const bounds = coords.reduce(
            (b, c) => b.extend(c as mapboxgl.LngLatLike),
            new mapboxgl.LngLatBounds(coords[0], coords[0])
          );
          map.fitBounds(bounds, { padding: 80, duration: 800 });
        }
      }
    } else {
      prevRouteIdRef.current = null;
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }, [route, tripActive, currentPosition]);

  // â”€â”€ Update origin/dest markers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    originMarkerRef.current?.remove();
    destMarkerRef.current?.remove();

    if (origin && !currentPosition) {
      // Only show origin marker when the user hasn't started moving yet.
      // Once advancing, the car marker replaces it visually.
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
  }, [origin, destination, currentPosition]);

  // â”€â”€ Update current position marker (car icon) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (currentPosition) {
      ensureCarMarkerCSS();
      if (!positionMarkerRef.current) {
        const el = createCarMarkerElement();
        positionMarkerRef.current = new mapboxgl.Marker({ element: el, anchor: "center" })
          .setLngLat([currentPosition.lng, currentPosition.lat])
          .addTo(map);
      } else {
        positionMarkerRef.current.setLngLat([currentPosition.lng, currentPosition.lat]);
        // No rotation â€” car keeps its default orientation
      }
    } else {
      positionMarkerRef.current?.remove();
      positionMarkerRef.current = null;
    }
  }, [currentPosition, simBearing]);

  // â”€â”€ Follow-camera: nav-mode tracking during active trip â”€â”€â”€â”€
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
              new mapboxgl.LngLatBounds(coords[0], coords[0])
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

  // â”€â”€ Update hazard polygons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(HAZARD_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    const features = hazardZones.map((hz) => ({
      type: "Feature" as const,
      properties: { hazard_id: hz.hazard_id, hazard_type: hz.hazard_type, severity: hz.severity },
      geometry: hz.polygon,
    }));
    source.setData({ type: "FeatureCollection", features });
  }, [hazardZones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(CITY_STATE_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    const recentHistory = stepHistory.slice(-10);
    const features = recentHistory.flatMap(({ stepIndex, step }) => {
      const rawAreas = extractCityStateAreas(step.cityStateRaw);
      const areas = collapseNearbyDisplayNodes(
        compressIntoHighDangerZones(rawAreas, stepIndex),
        stepIndex,
        260
      );
      return areas.map((area, index) => ({
        type: "Feature" as const,
        id: "city-impact-" + stepIndex + "-" + index,
        properties: {
          impact_type: area.impact_type,
          severity: area.severity,
          danger_to_remain: area.danger_to_remain,
          status: area.status,
          radius_m: area.radius_m,
          node_id: area.node_id ?? "",
          source_kind: area.source_kind ?? "unknown",
          source_refs: (area.source_refs ?? []).join(","),
          step_index: stepIndex,
          icon: toImpactIcon(area.impact_type),
        },
        geometry: {
          type: "Point" as const,
          coordinates: [area.lon, area.lat] as [number, number],
        },
      }));
    });
    source.setData({ type: "FeatureCollection", features });
  }, [mapReadyVersion, stepHistory]);

  const lastSyncedStepRef = useRef<number | null>(null);
  const syncedHazardsRef = useRef<
    Map<string, { hazardId: string; lastSeenStep: number; persistent: boolean; hazardType: string }>
  >(new Map());
  useEffect(() => {
    if (lastSyncedStepRef.current === currentStepIndex) {
      return;
    }
    lastSyncedStepRef.current = currentStepIndex;

    let cancelled = false;

    async function syncCityStateHazards() {
      const stepAreas = collapseNearbyDisplayNodes(
        compressIntoHighDangerZones(extractCityStateAreas(currentStep.cityStateRaw), currentStepIndex),
        currentStepIndex,
        240
      );
      const persistStepsFor = (hazardType: string) => {
        if (hazardType === "roadblock") return 9;
        if (hazardType === "flood") return 3;
        if (hazardType === "wind") return 2;
        return 4;
      };
      const keyFor = (hazardType: string, lat: number, lon: number) =>
        `${hazardType}:${Math.round(lat * 350) / 350}:${Math.round(lon * 350) / 350}`;
      const radiusForHazard = (hazardType: string, radius: number) => {
        if (hazardType === "roadblock") return Math.max(60, Math.min(1400, radius));
        if (hazardType === "flood") return Math.max(60, Math.min(900, radius));
        if (hazardType === "wind") return Math.max(60, Math.min(800, radius));
        return Math.max(60, Math.min(1000, radius));
      };

      try {
        const tracked = syncedHazardsRef.current;
        if (currentStepIndex === 0) {
          const activeAtStart = await getActiveHazards();
          await Promise.all(
            activeAtStart.map((hazard) => deactivateHazard(hazard.hazard_id).catch(() => undefined))
          );
          tracked.clear();
        }
        const desired = new Set<string>();
        let changed = false;

        for (const area of stepAreas) {
          if (cancelled) return;
          const hazardType = toHazardType(area.impact_type, area.severity);
          if (!hazardType) {
            continue;
          }
          const key = keyFor(hazardType, area.lat, area.lon);
          desired.add(key);
          const persistent = area.impact_type === "road_closure" || area.severity >= 86;
          const existing = tracked.get(key);
          if (existing) {
            existing.lastSeenStep = currentStepIndex;
            existing.persistent = existing.persistent || persistent;
            continue;
          }
          const created = await reportHazard(
            hazardType,
            { lat: area.lat, lng: area.lon },
            "step " + (currentStepIndex + 1) + ": " + area.impact_type,
            radiusForHazard(hazardType, area.radius_m)
          );
          tracked.set(key, {
            hazardId: created.hazard_id,
            lastSeenStep: currentStepIndex,
            persistent,
            hazardType,
          });
          changed = true;
        }

        // No decay: once a hazard is added it stays on the map (can only get worse).

        if (changed) {
          await fetchHazards();
        }
        if (!cancelled && changed && routeRef.current) {
          refetch();
        }
      } catch {
        // no-op for demo resilience
      }
    }

    void syncCityStateHazards();
    return () => {
      cancelled = true;
    };
  }, [currentStep.cityStateRaw, currentStepIndex, fetchHazards, refetch]);

  // ── Incremental step-based position advancement ──────────────
  // Track distance traveled along the current route so that each step
  // advances incrementally (like Google Maps) rather than snapping to a
  // fraction of the whole route, which causes position jumps on reroute.
  const distanceTraveledRef = useRef<number>(0);
  const prevDemoRouteIdRef = useRef<string | null>(null);
  const prevStepIndexRef = useRef<number>(0);

  useEffect(() => {
    if (!route?.geometry?.coordinates?.length || totalSteps <= 1) {
      return;
    }
    const coords = route.geometry.coordinates as number[][];
    const { cumDist, totalDist } = buildCumulativeDistances(coords);

    if (totalDist === 0) return;

    const isReroute =
      prevDemoRouteIdRef.current !== null &&
      prevDemoRouteIdRef.current !== route.route_id;
    const isFirstRoute = prevDemoRouteIdRef.current === null;

    prevDemoRouteIdRef.current = route.route_id;

    if (isReroute) {
      // The new route starts from our current position (fixed in
      // useEvacuationRoute). Reset traveled distance and stay at coords[0].
      distanceTraveledRef.current = 0;
      const [lng, lat] = coords[0];
      setCurrentPosition({ lat, lng });
      prevStepIndexRef.current = currentStepIndex;
      return;
    }

    if (isFirstRoute && currentStepIndex === 0) {
      // Initial load: place user at the start of the route
      distanceTraveledRef.current = 0;
      const [lng, lat] = coords[0];
      setCurrentPosition({ lat, lng });
      prevStepIndexRef.current = 0;
      return;
    }

    // Normal step advancement
    const stepsRemaining = totalSteps - 1 - prevStepIndexRef.current;
    if (stepsRemaining <= 0 || currentStepIndex === prevStepIndexRef.current) {
      return;
    }

    const stepsTaken = currentStepIndex - prevStepIndexRef.current;
    const distRemaining = totalDist - distanceTraveledRef.current;
    const distPerStep = distRemaining / stepsRemaining;
    const advanceDist = distPerStep * stepsTaken;

    distanceTraveledRef.current = Math.min(
      totalDist,
      distanceTraveledRef.current + advanceDist
    );
    prevStepIndexRef.current = currentStepIndex;

    // Find position along route at this distance
    const targetDist = distanceTraveledRef.current;
    let posLng: number;
    let posLat: number;

    if (targetDist >= totalDist) {
      [posLng, posLat] = coords[coords.length - 1];
    } else {
      let segIdx = 0;
      for (let i = 1; i < cumDist.length; i++) {
        if (cumDist[i] >= targetDist) {
          segIdx = i - 1;
          break;
        }
      }
      const segStart = cumDist[segIdx];
      const segLen = cumDist[segIdx + 1] - segStart;
      const t = segLen > 0 ? (targetDist - segStart) / segLen : 0;
      const [lng1, lat1] = coords[segIdx];
      const [lng2, lat2] = coords[segIdx + 1];
      posLng = lng1 + t * (lng2 - lng1);
      posLat = lat1 + t * (lat2 - lat1);
    }

    setCurrentPosition({ lat: posLat, lng: posLng });
  }, [currentStepIndex, route?.route_id, route?.geometry, setCurrentPosition, totalSteps]);

  // â”€â”€ Rerouting: pulse route line â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Weather: toggle wind particle layer visibility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(WIND_LAYER)) return;
    map.setLayoutProperty(WIND_LAYER, "visibility", showWind ? "visible" : "none");
  }, [showWind]);

  // â”€â”€ Weather: toggle alert zones visibility + fetch data â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (map.getLayer(WEATHER_ALERT_FILL)) {
      map.setLayoutProperty(WEATHER_ALERT_FILL, "visibility", showWeatherAlerts ? "visible" : "none");
    }
    if (map.getLayer(WEATHER_ALERT_OUTLINE)) {
      map.setLayoutProperty(WEATHER_ALERT_OUTLINE, "visibility", showWeatherAlerts ? "visible" : "none");
    }
    if (showWeatherAlerts) {
      fetchWeatherZones()
        .then((fc) => {
          const source = map.getSource(WEATHER_ALERT_SOURCE) as mapboxgl.GeoJSONSource | undefined;
          if (source) {
            const filtered = { ...fc, features: fc.features.filter((f) => f.geometry) };
            source.setData(filtered as any);
          }
        })
        .catch(() => {});
    }
  }, [showWeatherAlerts]);

  // â”€â”€ Weather: fetch route weather when route changes â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    if (!route?.route_id || !showRouteWeather) {
      setRouteWeatherPoints([]);
      return;
    }
    fetchRouteWeather(route.route_id)
      .then(setRouteWeatherPoints)
      .catch(() => setRouteWeatherPoints([]));
  }, [route?.route_id, showRouteWeather]);

  // â”€â”€ Weather: render route weather markers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const map = mapRef.current;
    weatherMarkersRef.current.forEach((m) => m.remove());
    weatherMarkersRef.current = [];

    if (!map || !showRouteWeather || routeWeatherPoints.length === 0) return;

    for (const pt of routeWeatherPoints) {
      const temp = pt.temperature_c != null ? String(Math.round(pt.temperature_c)) + "C" : "";
      const wind =
        pt.wind_speed_kmh != null ? String(Math.round(pt.wind_speed_kmh)) + " km/h" : "";
      const precip = pt.precipitation_probability != null && pt.precipitation_probability > 0
        ? String(pt.precipitation_probability) + "%"
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

  // â”€â”€ Handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        const coord: Coordinate = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setOrigin(coord);
        setOriginText(formatCoord(coord));
      },
      () => {}
    );
  };

  const handleStartTrip = () => {
    setFollowCamera(true);
    startTrip();
  };

  const handleEndTrip = () => {
    endTrip();
  };

  const mapCenter: Coordinate | null = currentPosition ?? origin ?? destination ?? null;
  const inputsDisabled = tripActive;

  return (
    <View className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      {/* â”€â”€ Rerouting banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {rerouting && (
        <View className="z-10 bg-amber-500 px-4 py-2">
          <Text className="text-center text-sm font-semibold text-black">
            {tripActive
              ? "Warning: rerouting from your current position..."
              : "Warning: rerouting due to a new hazard on your path..."}
          </Text>
        </View>
      )}

      <View className="flex-1 flex-row">
        {!plannerCollapsed ? (
        <View
          className={`w-80 border-r p-4 ${isDark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-white"}`}
          // @ts-expect-error web-only overflow style
          style={{ minWidth: 320, overflowY: "auto" }}
        >
          <Text className={`mb-3 text-lg font-bold ${isDark ? "text-white" : "text-slate-900"}`}>
            Route Planner
          </Text>

          {/* Origin */}
          <Text className={`mb-1 text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Origin (lat, lng)
          </Text>
          <View className="mb-2 flex-row items-center gap-2">
            <TextInput
              className={`flex-1 rounded-lg px-3 py-2 text-sm ${
                isDark ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-900"
              } ${mapClickMode === "origin" ? "border-2 border-green-500" : ""}`}
              placeholder="43.706, -79.41"
              placeholderTextColor={isDark ? "#64748b" : "#94a3b8"}
              value={originText}
              onChangeText={setOriginText}
              editable={!inputsDisabled}
            />
            <Pressable
              onPress={() => setMapClickMode(mapClickMode === "origin" ? null : "origin")}
              disabled={inputsDisabled}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "origin" ? "bg-green-600" : isDark ? "bg-slate-700" : "bg-slate-200"
              }`}
            >
              <Text className={`text-xs ${mapClickMode === "origin" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}>
                Pick
              </Text>
            </Pressable>
          </View>
          {!inputsDisabled && (
            <Pressable onPress={handleUseCurrentLocation} className="mb-3">
              <Text className="text-xs text-blue-500">Use current location</Text>
            </Pressable>
          )}

          {/* Destination */}
          <Text className={`mb-1 text-xs font-medium ${isDark ? "text-slate-400" : "text-slate-500"}`}>
            Destination (lat, lng)
          </Text>
          <View className="mb-3 flex-row items-center gap-2">
            <TextInput
              className={`flex-1 rounded-lg px-3 py-2 text-sm ${
                isDark ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-900"
              } ${mapClickMode === "destination" ? "border-2 border-purple-500" : ""}`}
              placeholder="43.65, -79.38"
              placeholderTextColor={isDark ? "#64748b" : "#94a3b8"}
              value={destText}
              onChangeText={setDestText}
              editable={!inputsDisabled}
            />
            <Pressable
              onPress={() => setMapClickMode(mapClickMode === "destination" ? null : "destination")}
              disabled={inputsDisabled}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "destination" ? "bg-purple-600" : isDark ? "bg-slate-700" : "bg-slate-200"
              }`}
            >
              <Text className={`text-xs ${mapClickMode === "destination" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}>
                Set
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
                {loading ? "Planning..." : "Plan Route"}
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
            <View className={`mb-4 rounded-xl p-3 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}>
              <Text className={`mb-1 text-sm font-semibold ${isDark ? "text-white" : "text-slate-900"}`}>
                Route Details
              </Text>
              <Text className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                Distance: {formatDistance(route.distance_meters)}
              </Text>
              <Text className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                Duration: {formatDuration(route.duration_seconds)}
              </Text>
              {route.hazards_avoided.length > 0 && (
                <Text className="mt-1 text-xs text-amber-400">
                  Hazards avoided: {route.hazards_avoided.length}
                </Text>
              )}
              {route.instructions.length > 0 && (
                <View className="mt-2">
                  <Text className={`mb-1 text-xs font-medium ${isDark ? "text-slate-300" : "text-slate-600"}`}>
                    Directions
                  </Text>
                  {route.instructions.slice(0, 6).map((instr, i) => (
                    <Text key={i} className={`text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                      {i + 1}. {instr}
                    </Text>
                  ))}
                  {route.instructions.length > 6 && (
                    <Text className={`text-xs ${isDark ? "text-slate-500" : "text-slate-400"}`}>
                      +{route.instructions.length - 6} more...
                    </Text>
                  )}
                </View>
              )}
            </View>
          )}

          {/* â”€â”€ Trip controls â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
          {route && !tripActive && (
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
            <View className={`mb-4 rounded-xl p-3 ${isDark ? "bg-green-950/40" : "bg-green-50"}`}>
              <View className="mb-2 flex-row items-center gap-2">
                <View className="h-2 w-2 rounded-full bg-green-500" />
                <Text className={`text-xs font-semibold ${isDark ? "text-green-400" : "text-green-700"}`}>
                  Trip in Progress
                </Text>
              </View>

              {currentPosition && (
                <Text className={`mb-1 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Position: {formatCoord(currentPosition)}
                </Text>
              )}

              {/* Progress bar */}
              <View className={`mb-2 h-2 overflow-hidden rounded-full ${isDark ? "bg-slate-700" : "bg-slate-200"}`}>
                <View
                  className="h-full rounded-full bg-green-500"
                  style={{ width: `${Math.round(simProgress * 100)}%` }}
                />
              </View>
              <Text className={`mb-3 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
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
            <View className={`mb-3 rounded-xl p-3 ${isDark ? "bg-red-950/40" : "bg-red-50"}`}>
              <Text className={`text-xs font-medium ${isDark ? "text-red-400" : "text-red-600"}`}>
                {hazardZones.length} active hazard zone{hazardZones.length > 1 ? "s" : ""}
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

        </View>
        ) : null}

        {/* â”€â”€ Map container â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        <View className="flex-1" style={{ minHeight: 400, position: "relative" as any }}>
          <View
            style={{
              position: "absolute" as any,
              top: 10,
              left: 10,
              zIndex: 12,
            }}
          >
            <Pressable
              onPress={() => setPlannerCollapsed((prev) => !prev)}
              className={`h-10 w-10 items-center justify-center rounded-lg border ${
                isDark ? "border-slate-700 bg-slate-800" : "border-slate-200 bg-white"
              }`}
              accessibilityLabel={plannerCollapsed ? "Open route planner" : "Close route planner"}
            >
              <View className={`mb-1 h-0.5 w-4 rounded ${isDark ? "bg-slate-200" : "bg-slate-700"}`} />
              <View className={`mb-1 h-0.5 w-4 rounded ${isDark ? "bg-slate-200" : "bg-slate-700"}`} />
              <View className={`h-0.5 w-4 rounded ${isDark ? "bg-slate-200" : "bg-slate-700"}`} />
            </Pressable>
            <View className={`mt-1 rounded-md px-2 py-1 ${isDark ? "bg-slate-900/90" : "bg-white/90"}`}>
              <Text className={`text-[10px] ${isDark ? "text-slate-300" : "text-slate-600"}`}>
                Disaster step {currentStepIndex + 1}/{totalSteps}
              </Text>
            </View>
          </View>
          {/* Weather controls overlay */}
          {MAPBOX_PUBLIC_TOKEN && !mapError && (
            <View
              style={{
                position: "absolute" as any,
                top: 64,
                left: 10,
                zIndex: 10,
              }}
            >
              <View
                className={`rounded-lg ${isDark ? "bg-slate-900/90" : "bg-white/90"}`}
                style={{ paddingHorizontal: 10, paddingVertical: 6, gap: 4, backdropFilter: "blur(6px)" } as any}
              >
                <Text className={`text-xs font-semibold uppercase tracking-wide ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  Layers
                </Text>
                <Pressable
                  onPress={() => setShowWind((v) => !v)}
                  className={`flex-row items-center rounded px-2 py-1 ${showWind ? (isDark ? "bg-sky-900/50" : "bg-sky-100") : ""}`}
                >
                  <Text className={`text-xs ${showWind ? (isDark ? "text-sky-300" : "text-sky-700") : (isDark ? "text-slate-300" : "text-slate-600")}`}>
                    {showWind ? "[on]" : "[off]"} Wind
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => setShowWeatherAlerts((v) => !v)}
                  className={`flex-row items-center rounded px-2 py-1 ${showWeatherAlerts ? (isDark ? "bg-amber-900/50" : "bg-amber-100") : ""}`}
                >
                  <Text className={`text-xs ${showWeatherAlerts ? (isDark ? "text-amber-300" : "text-amber-700") : (isDark ? "text-slate-300" : "text-slate-600")}`}>
                    {showWeatherAlerts ? "[on]" : "[off]"} Alerts
                  </Text>
                </Pressable>
                {route && (
                  <Pressable
                    onPress={() => setShowRouteWeather((v) => !v)}
                    className={`flex-row items-center rounded px-2 py-1 ${showRouteWeather ? (isDark ? "bg-emerald-900/50" : "bg-emerald-100") : ""}`}
                  >
                    <Text className={`text-xs ${showRouteWeather ? (isDark ? "text-emerald-300" : "text-emerald-700") : (isDark ? "text-slate-300" : "text-slate-600")}`}>
                      {showRouteWeather ? "[on]" : "[off]"} Route Wx
                    </Text>
                  </Pressable>
                )}
              </View>
            </View>
          )}
          {mapError ? (
            <View className={`flex-1 items-center justify-center px-4 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}>
              <Text className={`mb-2 text-center text-sm font-medium ${isDark ? "text-red-400" : "text-red-600"}`}>
                Map failed to load
              </Text>
              <Text className={`text-center text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
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
            <View className={`flex-1 items-center justify-center px-4 ${isDark ? "bg-slate-800" : "bg-slate-50"}`}>
              <Text className={`text-center text-sm ${isDark ? "text-slate-300" : "text-slate-600"}`}>
                Mapbox token not set. Add EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN in frontend/.env.
              </Text>
            </View>
          )}
          <WeatherLayerOverlay
            map={mapRef.current}
            mapLoaded={mapIsLoaded}
            showWeatherAlerts={showWeatherAlerts}
            showWind={showWind}
            onToggleAlerts={() => setShowWeatherAlerts((v) => !v)}
            onToggleWind={() => setShowWind((v) => !v)}
            theme={theme}
            offsetTop={100}
          />
          <AlertSignalsLayer
            map={mapRef.current}
            mapLoaded={mapIsLoaded}
          />
        </View>
      </View>

      {/* â”€â”€ Report Hazard Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
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

