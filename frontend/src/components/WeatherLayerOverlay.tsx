import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, Text, View } from "react-native";
import {
  useDisasterDemo,
  AffectedArea,
  StormState,
} from "../state/DisasterDemoContext";
import { WeatherDatasetMetadata } from "../data/types";
import { DisasterStepData } from "../data/mock/disasterSteps";
import { AppTheme } from "../types/theme";
import mapboxgl from "mapbox-gl";
import { fetchAlertSignals, AlertSignalFeature } from "../services/api";

// Kept for backward-compat with MapScreen imports
export type WeatherLayerMode = "wind" | "alerts" | "route-weather" | null;

// ── Layer identifiers ────────────────────────────────────────────────────────
const HEATMAP_SOURCE = "disaster-heatmap";
const HEATMAP_LAYER = "disaster-heatmap-layer";
const FLOOD_SOURCE = "disaster-flood-heatmap";
const FLOOD_LAYER = "disaster-flood-heatmap-layer";

// ── Live alert signal layer identifiers ──────────────────────────────────────
const LIVE_ALERTS_SOURCE = "live-alerts-src";
const LIVE_ALERT_LAYERS: Record<string, string> = {
  earthquake: "live-alerts-earthquake",
  fire: "live-alerts-fire",
  storm: "live-alerts-storm",
  flood: "live-alerts-flood",
  general: "live-alerts-general",
};
const LIVE_ALERTS_HOVER_SOURCE = "live-alerts-hover-src";
const LIVE_ALERTS_HOVER_LAYER  = "live-alerts-hover-circles";

// ── Disaster typing ──────────────────────────────────────────────────────────
type DisasterType = "storm" | "flood" | "fire" | "earthquake" | "general";

interface DisasterPalette {
  label: string;
  accentColor: string;
  gradient: string;
  mapboxColors: unknown[];
}

const DISASTER_PALETTES: Record<DisasterType, DisasterPalette> = {
  storm: {
    label: "Tropical Storm",
    accentColor: "#22d3ee",
    gradient:
      "linear-gradient(90deg, rgba(43,95,184,0.85) 0%, rgba(34,184,200,1) 40%, rgba(255,230,50,1) 75%, #ffffff 100%)",
    mapboxColors: [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(0,0,0,0)",
      0.15,
      "rgba(43,95,184,0.55)",
      0.35,
      "rgba(34,184,200,0.8)",
      0.55,
      "rgba(80,210,220,0.9)",
      0.75,
      "rgba(255,230,50,1)",
      1.0,
      "rgba(255,255,255,1)",
    ],
  },
  flood: {
    label: "Flood Risk",
    accentColor: "#3b82f6",
    gradient:
      "linear-gradient(90deg, rgba(8,48,107,0.85) 0%, rgba(33,113,181,1) 55%, rgba(198,219,239,1) 100%)",
    mapboxColors: [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(0,0,0,0)",
      0.15,
      "rgba(8,48,107,0.55)",
      0.35,
      "rgba(8,81,156,0.8)",
      0.55,
      "rgba(33,113,181,0.9)",
      0.75,
      "rgba(66,146,198,1)",
      1.0,
      "rgba(198,219,239,1)",
    ],
  },
  fire: {
    label: "Wildfire",
    accentColor: "#f97316",
    gradient:
      "linear-gradient(90deg, rgba(255,255,100,0.85) 0%, rgba(255,120,0,1) 55%, rgba(120,0,0,1) 100%)",
    mapboxColors: [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(0,0,0,0)",
      0.15,
      "rgba(255,255,120,0.55)",
      0.35,
      "rgba(255,200,0,0.8)",
      0.55,
      "rgba(255,120,0,0.9)",
      0.75,
      "rgba(200,40,0,1)",
      1.0,
      "rgba(120,0,0,1)",
    ],
  },
  earthquake: {
    label: "Seismic Activity",
    accentColor: "#a855f7",
    gradient:
      "linear-gradient(90deg, rgba(180,120,255,0.85) 0%, rgba(100,40,200,1) 60%, rgba(20,0,80,1) 100%)",
    mapboxColors: [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(0,0,0,0)",
      0.15,
      "rgba(180,120,255,0.55)",
      0.35,
      "rgba(140,80,255,0.8)",
      0.55,
      "rgba(100,40,200,0.9)",
      0.75,
      "rgba(60,0,140,1)",
      1.0,
      "rgba(20,0,80,1)",
    ],
  },
  general: {
    label: "Disaster Zone",
    accentColor: "#ef4444",
    gradient:
      "linear-gradient(90deg, rgba(103,169,207,0.85) 0%, rgba(239,138,98,1) 60%, rgba(178,24,43,1) 100%)",
    mapboxColors: [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0,
      "rgba(0,0,0,0)",
      0.15,
      "rgba(103,169,207,0.55)",
      0.35,
      "rgba(209,229,240,0.8)",
      0.55,
      "rgba(253,219,199,0.9)",
      0.75,
      "rgba(239,138,98,1)",
      1.0,
      "rgba(178,24,43,1)",
    ],
  },
};

// ── Statistical helpers ───────────────────────────────────────────────────────

/** Box-Muller: returns one standard-normal sample */
function randn(): number {
  let u = 0,
    v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

interface GeoJSONPoint {
  type: "Feature";
  geometry: { type: "Point"; coordinates: number[] };
  properties: { weight: number; category?: string };
}

type FeatureCollection = {
  type: "FeatureCollection";
  features: GeoJSONPoint[];
};

/**
 * Generates a fine-grained storm heatmap using:
 * - An anisotropic bivariate Gaussian background cloud
 * - Discrete wind-band rings at r34 / r50 / r64 / eyewall radii
 * - High-intensity clusters at each focus point
 */
function buildStormGeoJSON(storm: StormState, N = 800): FeatureCollection {
  const { center, windRadiiKm, focusPoints, movement, radiusOfMaxWindKm } =
    storm;

  const KM_PER_LAT = 111;
  const KM_PER_LON = 111 * Math.cos((center.lat * Math.PI) / 180);

  const r34 = windRadiiKm.r34;
  const r50 = windRadiiKm.r50;
  const r64 = windRadiiKm.r64;
  // Eyewall at radius-of-max-wind; fall back to fraction of r50
  const rmw =
    radiusOfMaxWindKm > 0 ? radiusOfMaxWindKm : r50 > 0 ? r50 * 0.28 : 0;

  // Outer sigma: keep background cloud tightly inside r50 (not r34) so the
  // heatmap footprint matches the storm's core rather than its full gale radius.
  const sigmaKm = r50 > 0 ? r50 * 0.55 : r34 > 0 ? r34 * 0.22 : 10;

  // Elongation along movement direction
  const speedFactor = movement ? Math.min(1.6, 1 + movement.speed_kmh / 60) : 1;
  const movAngle = movement
    ? ((90 - movement.direction_deg) * Math.PI) / 180
    : 0;
  const cosA = Math.cos(movAngle);
  const sinA = Math.sin(movAngle);

  const features: GeoJSONPoint[] = [];

  // ── Background anisotropic Gaussian cloud ────────────────────────
  for (let i = 0; i < N; i++) {
    const uAligned = randn() * sigmaKm * speedFactor;
    const vPerp = randn() * sigmaKm * 0.72;
    const dxKm = uAligned * cosA - vPerp * sinA;
    const dyKm = uAligned * sinA + vPerp * cosA;
    const distKm = Math.sqrt(dxKm ** 2 + dyKm ** 2);
    const sigma50 = r50 > 0 ? r50 : sigmaKm * 0.5;
    const weight = Math.max(
      0.05,
      Math.exp(-(distKm ** 2) / (2 * sigma50 ** 2)),
    );
    features.push({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [
          center.lon + dxKm / KM_PER_LON,
          center.lat + dyKm / KM_PER_LAT,
        ],
      },
      properties: { weight },
    });
  }

  // ── Wind-band ring helper ────────────────────────────────────────
  function addRing(
    radiusKm: number,
    count: number,
    baseWeight: number,
    jitterFraction: number,
  ) {
    const jitterKm = radiusKm * jitterFraction;
    for (let i = 0; i < count; i++) {
      // Evenly-spaced angle with a tiny random perturbation for natural look
      const angle = (2 * Math.PI * i) / count + (Math.random() - 0.5) * 0.15;
      const r = radiusKm + randn() * jitterKm;
      const dxKm = r * Math.cos(angle);
      const dyKm = r * Math.sin(angle);
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [
            center.lon + dxKm / KM_PER_LON,
            center.lat + dyKm / KM_PER_LAT,
          ],
        },
        properties: { weight: baseWeight * (0.85 + Math.random() * 0.15) },
      });
    }
  }

  // Eyewall (peak winds, highest weight)
  if (rmw > 1) addRing(rmw, 140, 1.0, 0.1);
  // 64-kt destructive-wind radius
  if (r64 > 0) addRing(r64, 110, 0.82, 0.08);
  // 50-kt damaging-wind radius
  if (r50 > 0) addRing(r50, 130, 0.62, 0.1);
  // 34-kt gale-wind outer boundary
  if (r34 > 0) addRing(r34, 150, 0.38, 0.12);

  // ── Focus-point clusters (convective cores, rain bands) ──────────
  // Only render focus points that lie within r34 of the storm center —
  // points further out are artefacts of the data and would bloat the heatmap.
  const outerBoundKm = r34 > 0 ? r34 : r50 * 2;
  focusPoints.forEach((fp) => {
    const fpDxKm = (fp.lon - center.lon) * KM_PER_LON;
    const fpDyKm = (fp.lat - center.lat) * KM_PER_LAT;
    const fpDistKm = Math.sqrt(fpDxKm ** 2 + fpDyKm ** 2);
    if (fpDistKm > outerBoundKm) return; // skip out-of-bounds focus points

    const clusterSigmaKm = Math.max(0.5, sigmaKm * 0.15);
    for (let i = 0; i < 60; i++) {
      const dx = randn() * clusterSigmaKm;
      const dy = randn() * clusterSigmaKm;
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [fp.lon + dx / KM_PER_LON, fp.lat + dy / KM_PER_LAT],
        },
        properties: { weight: 0.88 + Math.random() * 0.12 },
      });
    }
  });

  return { type: "FeatureCollection", features };
}

/**
 * Generates a dense, uniformly-filled flood heatmap.
 * Points are distributed evenly across the flood area (not Gaussian) so the
 * heatmap renders as a solid connected zone rather than sparse clusters.
 * Weight falls off from the area centre outward to suggest depth/severity.
 */
function buildFloodGeoJSON(areas: AffectedArea[]): FeatureCollection | null {
  const flooding = areas.filter((a) => a.impact_type === "flooding");
  if (!flooding.length) return null;

  const KM_PER_LAT = 111;
  const features: GeoJSONPoint[] = [];

  flooding.forEach((area) => {
    const KM_PER_LON = 111 * Math.cos((area.lat * Math.PI) / 180);
    const radiusKm = Math.max(0.15, area.radius_m / 1000);
    const baseWeight = Math.min(1, area.severity / 100);
    // Dense enough that points at this radius overlap at typical zoom levels
    const pointCount = Math.max(60, Math.round(area.severity * 1.5));

    for (let i = 0; i < pointCount; i++) {
      // Uniform disk sampling: sqrt of uniform random gives even areal density
      const r = radiusKm * Math.sqrt(Math.random());
      const angle = Math.random() * 2 * Math.PI;
      const dxKm = r * Math.cos(angle);
      const dyKm = r * Math.sin(angle);
      // Weight highest at centre, fading toward edge — simulates flood depth
      const distFraction = r / radiusKm;
      const weight =
        baseWeight * (1 - distFraction * 0.5) * (0.85 + Math.random() * 0.15);
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [
            area.lon + dxKm / KM_PER_LON,
            area.lat + dyKm / KM_PER_LAT,
          ],
        },
        properties: { weight: Math.min(1, weight) },
      });
    }
  });

  return { type: "FeatureCollection", features };
}

// ── Live alert signal helpers ─────────────────────────────────────────────────

function categorizeSignal(signalType: string): string {
  const t = (signalType ?? "").toLowerCase();
  if (t.includes("earthquake") || t.includes("seismic") || t.includes("quake"))
    return "earthquake";
  if (t.includes("fire") || t.includes("wildfire")) return "fire";
  if (
    t.includes("storm") ||
    t.includes("hurricane") ||
    t.includes("cyclone") ||
    t.includes("typhoon") ||
    t.includes("tropical")
  )
    return "storm";
  if (t.includes("flood")) return "flood";
  return "general";
}

function signalSeverityWeight(severity: string): number {
  switch ((severity ?? "").toLowerCase()) {
    case "extreme":
    case "red":
      return 1.0;
    case "severe":
    case "high":
      return 0.75;
    case "moderate":
    case "medium":
    case "orange":
      return 0.55;
    case "low":
    case "green":
      return 0.25;
    default:
      return 0.45;
  }
}

const ALERT_SCATTER_RADIUS: Record<string, number> = {
  earthquake: 0.08,
  fire: 0.05,
  storm: 0.45,
  flood: 0.12,
  general: 0.15,
};
const ALERT_SCATTER_COUNT: Record<string, number> = {
  earthquake: 35,
  fire: 30,
  storm: 55,
  flood: 45,
  general: 30,
};
const ALERT_RADIUS_EXPR: Record<string, unknown[]> = {
  earthquake: ["interpolate", ["linear"], ["zoom"], 0, 4, 5, 14, 9, 28],
  fire: ["interpolate", ["linear"], ["zoom"], 0, 5, 5, 18, 9, 40],
  storm: ["interpolate", ["linear"], ["zoom"], 0, 8, 5, 28, 9, 60],
  flood: ["interpolate", ["linear"], ["zoom"], 0, 7, 5, 22, 9, 48],
  general: ["interpolate", ["linear"], ["zoom"], 0, 5, 5, 16, 9, 32],
};

function buildAlertGeoJSON(features: AlertSignalFeature[]): FeatureCollection {
  const pts: GeoJSONPoint[] = [];
  for (const feat of features) {
    const p = feat.properties;

    // Prefer geometry coordinates (GeoJSON standard); fall back to properties
    let lon: number | null = null;
    let lat: number | null = null;
    const coords = feat.geometry?.coordinates as number[] | undefined;
    if (Array.isArray(coords) && coords.length >= 2) {
      [lon, lat] = coords;
    } else {
      lon = p.longitude ?? null;
      lat = p.latitude ?? null;
    }
    if (lon == null || lat == null) continue;

    const cat    = categorizeSignal(p.signal_type);
    const baseW  = signalSeverityWeight(p.severity);
    const radius = ALERT_SCATTER_RADIUS[cat] ?? 0.15;
    const count  = ALERT_SCATTER_COUNT[cat] ?? 30;
    for (let i = 0; i < count; i++) {
      pts.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [lon + randn() * radius, lat + randn() * radius],
        },
        properties: {
          weight: Math.min(1, baseW * (0.75 + Math.random() * 0.25)),
          category: cat,
        },
      });
    }
  }
  return { type: "FeatureCollection", features: pts };
}

// ── Hover popup helpers ───────────────────────────────────────────────────────

/** One point per original signal — used for mouse interaction, not the heatmap. */
function buildHoverGeoJSON(features: AlertSignalFeature[]) {
  return {
    type: "FeatureCollection" as const,
    features: features
      .map((feat) => {
        const p = feat.properties;
        const coords = feat.geometry?.coordinates as number[] | undefined;
        let lon: number | null = null;
        let lat: number | null = null;
        if (Array.isArray(coords) && coords.length >= 2) {
          [lon, lat] = coords;
        } else {
          lon = p.longitude ?? null;
          lat = p.latitude ?? null;
        }
        if (lon == null || lat == null) return null;
        return {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [lon, lat] },
          properties: {
            signal_type: p.signal_type ?? "",
            value:       p.value ?? "",
            severity:    p.severity ?? "",
            source:      p.source ?? "",
            region:      p.region ?? "",
          },
        };
      })
      .filter((f): f is NonNullable<typeof f> => f !== null),
  };
}

function formatSource(src: string): string {
  const MAP: Record<string, string> = {
    usgs: "USGS", "nasa-firms": "NASA FIRMS", "noaa-nws": "NOAA NWS", gdacs: "GDACS",
  };
  return MAP[src] ?? src.toUpperCase();
}

function formatSignalType(t: string): string {
  return (t ?? "")
    .split(/[\s_-]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function severityHex(severity: string): string {
  switch ((severity ?? "").toLowerCase()) {
    case "extreme": case "red":    return "#ef4444";
    case "severe":  case "high":   return "#f97316";
    case "moderate":case "medium": case "orange": return "#f59e0b";
    case "low":     case "green":  return "#22c55e";
    default: return "#94a3b8";
  }
}

function buildPopupHTML(props: Record<string, string>): string {
  const color = severityHex(props.severity);
  const title = formatSignalType(props.signal_type);
  const sev   = (props.severity ?? "unknown").toUpperCase();
  const src   = formatSource(props.source);
  return `
    <div style="font-family:system-ui;font-size:13px;max-width:230px;padding:2px 0;">
      <div style="font-weight:700;font-size:14px;color:#f1f5f9;margin-bottom:5px;">${title}</div>
      ${props.value ? `<div style="color:#cbd5e1;line-height:1.4;margin-bottom:7px;">${props.value}</div>` : ""}
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
        <span style="background:${color}22;color:${color};padding:2px 8px;border-radius:999px;
                     font-size:11px;font-weight:700;border:1px solid ${color}55;">${sev}</span>
        <span style="color:#64748b;font-size:11px;">${src}</span>
      </div>
      ${props.region ? `<div style="color:#64748b;font-size:11px;margin-top:4px;">${props.region}</div>` : ""}
    </div>`;
}

// ── Disaster-type detection ──────────────────────────────────────────────────

function detectDisasterType(
  currentStep: DisasterStepData,
  stormState: StormState | null,
  metadata: WeatherDatasetMetadata | null,
): DisasterType {
  if (stormState) return "storm";

  const corpus = [
    ...currentStep.alerts.map(
      (a: { title: string; details: string }) => `${a.title} ${a.details}`,
    ),
    ...currentStep.weather.map(
      (w: { headline: string; details: string }) =>
        `${w.headline} ${w.details}`,
    ),
    metadata?.scenario_note ?? "",
  ]
    .join(" ")
    .toLowerCase();

  if (corpus.includes("fire") || corpus.includes("wildfire")) return "fire";
  if (corpus.includes("flood")) return "flood";
  if (
    corpus.includes("earthquake") ||
    corpus.includes("quake") ||
    corpus.includes("seismic")
  )
    return "earthquake";
  if (
    corpus.includes("storm") ||
    corpus.includes("cyclone") ||
    corpus.includes("hurricane") ||
    corpus.includes("typhoon")
  )
    return "storm";

  return "general";
}

// ── Shared paint configs ──────────────────────────────────────────────────────

/** Baseline r34 the original dataset was built around (km). */
const BASELINE_R34_KM = 56;

/**
 * Compute heatmap-radius scaled to the storm's actual r34.
 * Base pixel sizes are intentionally small so individual points remain
 * visually distinct; density/overlap creates the intensity gradient.
 */
function stormHeatmapRadius(r34Km: number) {
  const scale = r34Km > 0 ? r34Km / BASELINE_R34_KM : 1;
  return [
    "interpolate",
    ["linear"],
    ["zoom"],
    0,
    Math.max(2, Math.round(4 * scale)),
    5,
    Math.max(5, Math.round(12 * scale)),
    9,
    Math.max(8, Math.round(22 * scale)),
  ];
}

function buildStormPaint(r34Km: number) {
  return {
    "heatmap-weight": [
      "interpolate",
      ["linear"],
      ["get", "weight"],
      0,
      0,
      1,
      1,
    ],
    "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 2],
    "heatmap-radius": stormHeatmapRadius(r34Km),
    "heatmap-opacity": 0.8,
  };
}

const FLOOD_PAINT_BASE = {
  "heatmap-weight": ["interpolate", ["linear"], ["get", "weight"], 0, 0, 1, 1],
  "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 3],
  // Larger radius than storm so neighbouring flood points blend into a solid zone
  "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 8, 5, 25, 9, 55],
  "heatmap-opacity": 0.75,
} as const;

const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

// ── Component ────────────────────────────────────────────────────────────────

export interface WeatherLayerOverlayProps {
  map: any;
  mapLoaded: boolean;
  showWeatherAlerts?: boolean;
  showWind?: boolean;
  onToggleAlerts?: (on: boolean) => void;
  onToggleWind?: (on: boolean) => void;
  theme?: AppTheme;
}

// Static palettes for the pass-through toggles (controlled by MapScreen)
const ALERT_LAYER_META: DisasterPalette = {
  label: "Hazard Alerts",
  accentColor: "#f59e0b",
  gradient:
    "linear-gradient(90deg, rgba(251,191,36,0.85) 0%, rgba(239,68,68,1) 60%, rgba(127,29,29,1) 100%)",
  mapboxColors: [],
};
const WIND_LAYER_META: DisasterPalette = {
  label: "Wind Layer",
  accentColor: "#818cf8",
  gradient:
    "linear-gradient(90deg, rgba(199,210,254,0.85) 0%, rgba(129,140,248,1) 55%, rgba(67,56,202,1) 100%)",
  mapboxColors: [],
};

export function WeatherLayerOverlay({
  map,
  mapLoaded,
  showWeatherAlerts = false,
  showWind = false,
  onToggleAlerts,
  onToggleWind,
  theme = "dark",
}: WeatherLayerOverlayProps) {
  const isDark = theme === "dark";
  const panelBg = isDark ? "rgba(15,23,42,0.92)" : "rgba(255,255,255,0.95)";
  const panelBorder = isDark ? "rgba(148,163,184,0.18)" : "rgba(71,85,105,0.2)";
  const titleColor = isDark ? "#f1f5f9" : "#0f172a";
  const iconColor = isDark ? "#94a3b8" : "#64748b";
  const chevronColor = isDark ? "#64748b" : "#94a3b8";
  const { currentStep, stormState, weatherDatasetMetadata, cityAffectedAreas } =
    useDisasterDemo();

  const [showStorm, setShowStorm] = useState(true);
  const [showFlood, setShowFlood] = useState(true);
  const [collapsed, setCollapsed] = useState(true);

  // Live alert signals state
  const [alertGeoJSON, setAlertGeoJSON] = useState<FeatureCollection>(EMPTY_FC);
  const [alertHoverGeoJSON, setAlertHoverGeoJSON] = useState<ReturnType<typeof buildHoverGeoJSON>>({ type: "FeatureCollection", features: [] });
  const [alertVisible, setAlertVisible] = useState<Record<string, boolean>>({});
  const popupRef = useRef<mapboxgl.Popup | null>(null);

  const disasterType = useMemo(
    () => detectDisasterType(currentStep, stormState, weatherDatasetMetadata),
    [currentStep, stormState, weatherDatasetMetadata],
  );

  const stormPalette = DISASTER_PALETTES[disasterType];
  const floodPalette = DISASTER_PALETTES.flood;

  const stormData = useMemo(
    () => (stormState ? buildStormGeoJSON(stormState) : null),
    [stormState],
  );

  const floodData = useMemo(
    () => buildFloodGeoJSON(cityAffectedAreas),
    [cityAffectedAreas],
  );

  // ── Storm layer: setup / teardown ─────────────────────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    if (!map.getSource(HEATMAP_SOURCE)) {
      map.addSource(HEATMAP_SOURCE, {
        type: "geojson",
        data: stormData ?? EMPTY_FC,
      });
    }
    if (!map.getLayer(HEATMAP_LAYER)) {
      map.addLayer({
        id: HEATMAP_LAYER,
        type: "heatmap",
        source: HEATMAP_SOURCE,
        paint: {
          ...buildStormPaint(stormState?.windRadiiKm.r34 ?? BASELINE_R34_KM),
          "heatmap-color": stormPalette.mapboxColors,
        },
      });
    }
    return () => {
      try {
        if (map.getLayer(HEATMAP_LAYER)) map.removeLayer(HEATMAP_LAYER);
        if (map.getSource(HEATMAP_SOURCE)) map.removeSource(HEATMAP_SOURCE);
      } catch {
        /* map destroyed */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, mapLoaded]);

  // Storm: update data
  useEffect(() => {
    if (!map || !mapLoaded) return;
    (map.getSource(HEATMAP_SOURCE) as any)?.setData(stormData ?? EMPTY_FC);
  }, [map, mapLoaded, stormData]);

  // Storm: update color when type changes
  useEffect(() => {
    if (!map || !mapLoaded || !map.getLayer(HEATMAP_LAYER)) return;
    map.setPaintProperty(
      HEATMAP_LAYER,
      "heatmap-color",
      stormPalette.mapboxColors,
    );
  }, [map, mapLoaded, disasterType, stormPalette]);

  // Storm: update radius when storm scale changes
  useEffect(() => {
    if (!map || !mapLoaded || !map.getLayer(HEATMAP_LAYER)) return;
    map.setPaintProperty(
      HEATMAP_LAYER,
      "heatmap-radius",
      stormHeatmapRadius(stormState?.windRadiiKm.r34 ?? BASELINE_R34_KM),
    );
  }, [map, mapLoaded, stormState]);

  // Storm: toggle visibility
  useEffect(() => {
    if (!map || !mapLoaded || !map.getLayer(HEATMAP_LAYER)) return;
    map.setLayoutProperty(
      HEATMAP_LAYER,
      "visibility",
      showStorm ? "visible" : "none",
    );
  }, [map, mapLoaded, showStorm]);

  // ── Flood layer: setup / teardown ─────────────────────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    if (!map.getSource(FLOOD_SOURCE)) {
      map.addSource(FLOOD_SOURCE, {
        type: "geojson",
        data: floodData ?? EMPTY_FC,
      });
    }
    if (!map.getLayer(FLOOD_LAYER)) {
      map.addLayer({
        id: FLOOD_LAYER,
        type: "heatmap",
        source: FLOOD_SOURCE,
        paint: {
          ...FLOOD_PAINT_BASE,
          "heatmap-color": floodPalette.mapboxColors,
        },
      });
    }
    return () => {
      try {
        if (map.getLayer(FLOOD_LAYER)) map.removeLayer(FLOOD_LAYER);
        if (map.getSource(FLOOD_SOURCE)) map.removeSource(FLOOD_SOURCE);
      } catch {
        /* map destroyed */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, mapLoaded]);

  // Flood: update data
  useEffect(() => {
    if (!map || !mapLoaded) return;
    (map.getSource(FLOOD_SOURCE) as any)?.setData(floodData ?? EMPTY_FC);
  }, [map, mapLoaded, floodData]);

  // Flood: toggle visibility
  useEffect(() => {
    if (!map || !mapLoaded || !map.getLayer(FLOOD_LAYER)) return;
    map.setLayoutProperty(
      FLOOD_LAYER,
      "visibility",
      showFlood ? "visible" : "none",
    );
  }, [map, mapLoaded, showFlood]);

  // ── Live alert signals: fetch ─────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const col = await fetchAlertSignals();
        console.log("Fetched alert signals:", col.features.length);
        const geoJSON = buildAlertGeoJSON(col.features);
        const cats = new Set(
          geoJSON.features.map((f) => f.properties.category!),
        );
        setAlertGeoJSON(geoJSON);
        setAlertHoverGeoJSON(buildHoverGeoJSON(col.features));
        setAlertVisible((prev) => {
          const next: Record<string, boolean> = {};
          for (const cat of cats) next[cat] = prev[cat] ?? true;
          return next;
        });
      } catch {
        /* non-critical */
      }
    }
    load();
    const interval = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Live alert signals: setup / teardown layers ───────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    if (!map.getSource(LIVE_ALERTS_SOURCE)) {
      map.addSource(LIVE_ALERTS_SOURCE, { type: "geojson", data: EMPTY_FC });
    }
    for (const [cat, layerId] of Object.entries(LIVE_ALERT_LAYERS)) {
      if (!map.getLayer(layerId)) {
        const palette =
          DISASTER_PALETTES[cat as DisasterType] ?? DISASTER_PALETTES.general;
        map.addLayer({
          id: layerId,
          type: "heatmap",
          source: LIVE_ALERTS_SOURCE,
          filter: ["==", ["get", "category"], cat],
          paint: {
            "heatmap-weight": [
              "interpolate",
              ["linear"],
              ["get", "weight"],
              0,
              0,
              1,
              1,
            ],
            "heatmap-intensity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              0,
              1,
              9,
              2.5,
            ],
            "heatmap-radius": ALERT_RADIUS_EXPR[cat],
            "heatmap-opacity": 0.72,
            "heatmap-color": palette.mapboxColors,
          },
        });
      }
    }
    // ── Hover source + invisible circle layer for mouse interaction ──
    if (!map.getSource(LIVE_ALERTS_HOVER_SOURCE)) {
      map.addSource(LIVE_ALERTS_HOVER_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
    }
    if (!map.getLayer(LIVE_ALERTS_HOVER_LAYER)) {
      map.addLayer({
        id: LIVE_ALERTS_HOVER_LAYER,
        type: "circle",
        source: LIVE_ALERTS_HOVER_SOURCE,
        paint: {
          "circle-radius": 18,
          "circle-opacity": 0,
          "circle-stroke-width": 0,
        },
      });
    }

    // ── Mouse events ──────────────────────────────────────────────────
    const onEnter = (e: mapboxgl.MapMouseEvent & { features?: mapboxgl.GeoJSONFeature[] }) => {
      map.getCanvas().style.cursor = "pointer";
      const feat = e.features?.[0];
      if (!feat) return;
      const props = feat.properties as Record<string, string>;
      popupRef.current?.remove();
      popupRef.current = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 12,
        maxWidth: "260px",
        className: "alert-signal-popup",
      })
        .setLngLat(e.lngLat)
        .setHTML(buildPopupHTML(props))
        .addTo(map);
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
      popupRef.current?.remove();
      popupRef.current = null;
    };
    map.on("mouseenter", LIVE_ALERTS_HOVER_LAYER, onEnter);
    map.on("mouseleave", LIVE_ALERTS_HOVER_LAYER, onLeave);

    return () => {
      try {
        map.off("mouseenter", LIVE_ALERTS_HOVER_LAYER, onEnter);
        map.off("mouseleave", LIVE_ALERTS_HOVER_LAYER, onLeave);
        popupRef.current?.remove();
        popupRef.current = null;
        if (map.getLayer(LIVE_ALERTS_HOVER_LAYER)) map.removeLayer(LIVE_ALERTS_HOVER_LAYER);
        if (map.getSource(LIVE_ALERTS_HOVER_SOURCE)) map.removeSource(LIVE_ALERTS_HOVER_SOURCE);
        for (const layerId of Object.values(LIVE_ALERT_LAYERS)) {
          if (map.getLayer(layerId)) map.removeLayer(layerId);
        }
        if (map.getSource(LIVE_ALERTS_SOURCE))
          map.removeSource(LIVE_ALERTS_SOURCE);
      } catch {
        /* map destroyed */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, mapLoaded]);

  // ── Live alert signals: update heatmap data ──────────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    (map.getSource(LIVE_ALERTS_SOURCE) as any)?.setData(alertGeoJSON);
  }, [map, mapLoaded, alertGeoJSON]);

  // ── Live alert signals: update hover source data ──────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    (map.getSource(LIVE_ALERTS_HOVER_SOURCE) as any)?.setData(alertHoverGeoJSON);
  }, [map, mapLoaded, alertHoverGeoJSON]);

  // ── Live alert signals: toggle visibility ────────────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;
    for (const [cat, layerId] of Object.entries(LIVE_ALERT_LAYERS)) {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(
          layerId,
          "visibility",
          (alertVisible[cat] ?? false) ? "visible" : "none",
        );
      }
    }
  }, [map, mapLoaded, alertVisible]);

  const hasAnyLayer =
    stormData ||
    floodData ||
    onToggleAlerts ||
    onToggleWind ||
    Object.keys(alertVisible).length > 0;
  if (!hasAnyLayer) return null;

  const activeCount =
    (showStorm && stormData ? 1 : 0) +
    (showFlood && floodData ? 1 : 0) +
    (showWeatherAlerts ? 1 : 0) +
    (showWind ? 1 : 0) +
    Object.values(alertVisible).filter(Boolean).length;

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: "absolute" as any,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 20,
      }}
    >
      {/* ── Floating panel: top-left, adjacent to sidebar ── */}
      <View
        style={{
          position: "absolute" as any,
          top: 12,
          left: 12,
        }}
      >
        <View
          style={{
            width: 248,
            backgroundColor: panelBg,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: panelBorder,
            overflow: "hidden" as any,
            ...({
              boxShadow: isDark
                ? "0 8px 24px rgba(0,0,0,0.45)"
                : "0 4px 16px rgba(0,0,0,0.12)",
            } as any),
          }}
        >
          {/* ── Collapse header ── */}
          <Pressable
            onPress={() => setCollapsed((v) => !v)}
            style={{
              flexDirection: "row",
              alignItems: "center",
              paddingHorizontal: 12,
              paddingVertical: 9,
              gap: 8,
            }}
          >
            {/* Stack icon */}
            <View style={{ width: 18, alignItems: "center" }}>
              {[0, 3, 6].map((offset) => (
                <View
                  key={offset}
                  style={{
                    width: 14,
                    height: 2,
                    borderRadius: 1,
                    backgroundColor: iconColor,
                    marginBottom: offset < 6 ? 2 : 0,
                  }}
                />
              ))}
            </View>

            <Text
              style={{
                color: titleColor,
                fontSize: 12,
                fontWeight: "700",
                flex: 1,
              }}
            >
              Map Layers
            </Text>

            {activeCount > 0 && (
              <View
                style={{
                  backgroundColor: "#3b82f680",
                  borderRadius: 999,
                  paddingHorizontal: 7,
                  paddingVertical: 2,
                  marginRight: 6,
                }}
              >
                <Text
                  style={{ color: "#93c5fd", fontSize: 10, fontWeight: "700" }}
                >
                  {activeCount} on
                </Text>
              </View>
            )}

            {/* Chevron */}
            <Text style={{ color: chevronColor, fontSize: 10 }}>
              {collapsed ? "▸" : "▾"}
            </Text>
          </Pressable>

          {/* ── Expanded layer rows ── */}
          {!collapsed && (
            <View
              style={{
                paddingHorizontal: 12,
                paddingBottom: 12,
                borderTopWidth: 1,
                borderTopColor: panelBorder,
                paddingTop: 10,
                gap: 12,
              }}
            >
              {stormData && (
                <LegendRow
                  palette={stormPalette}
                  active={showStorm}
                  isDark={isDark}
                  onToggle={() => setShowStorm((v) => !v)}
                />
              )}
              {floodData && (
                <LegendRow
                  palette={floodPalette}
                  active={showFlood}
                  isDark={isDark}
                  onToggle={() => setShowFlood((v) => !v)}
                />
              )}
              {onToggleAlerts && (
                <LegendRow
                  palette={ALERT_LAYER_META}
                  active={showWeatherAlerts}
                  isDark={isDark}
                  onToggle={() => onToggleAlerts(!showWeatherAlerts)}
                />
              )}
              {onToggleWind && (
                <LegendRow
                  palette={WIND_LAYER_META}
                  active={showWind}
                  isDark={isDark}
                  onToggle={() => onToggleWind(!showWind)}
                />
              )}
              {Object.keys(alertVisible).map((cat) => {
                const palette =
                  DISASTER_PALETTES[cat as DisasterType] ??
                  DISASTER_PALETTES.general;
                const liveLabel = `Live ${palette.label}`;
                return (
                  <LegendRow
                    key={cat}
                    palette={{ ...palette, label: liveLabel }}
                    active={alertVisible[cat]}
                    isDark={isDark}
                    onToggle={() =>
                      setAlertVisible((prev) => ({
                        ...prev,
                        [cat]: !prev[cat],
                      }))
                    }
                  />
                );
              })}
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

// ── Legend row ────────────────────────────────────────────────────────────────

function LegendRow({
  palette,
  active,
  isDark,
  onToggle,
}: {
  palette: DisasterPalette;
  active: boolean;
  isDark: boolean;
  onToggle: () => void;
}) {
  const labelColor = active
    ? isDark
      ? "#f8fafc"
      : "#0f172a"
    : isDark
      ? "#64748b"
      : "#94a3b8";
  const dotInactive = isDark ? "#475569" : "#cbd5e1";
  const pillBgOff = isDark ? "rgba(71,85,105,0.3)" : "rgba(148,163,184,0.2)";
  const pillBorderOff = isDark
    ? "rgba(71,85,105,0.5)"
    : "rgba(148,163,184,0.4)";
  const tickDim = active
    ? isDark
      ? "#94a3b8"
      : "#64748b"
    : isDark
      ? "#475569"
      : "#94a3b8";
  const tickMid = active ? (isDark ? "#f8fafc" : "#0f172a") : tickDim;

  return (
    <>
      {/* Header: dot + label + toggle pill */}
      <View
        style={{ flexDirection: "row", alignItems: "center", marginBottom: 8 }}
      >
        <View
          style={{
            width: 8,
            height: 8,
            borderRadius: 999,
            backgroundColor: active ? palette.accentColor : dotInactive,
            marginRight: 8,
            ...({
              boxShadow: active ? `0 0 6px ${palette.accentColor}` : "none",
            } as any),
          }}
        />
        <Text
          style={{
            color: labelColor,
            fontSize: 13,
            fontWeight: "700",
            flex: 1,
          }}
        >
          {palette.label}
        </Text>
        <Pressable
          onPress={onToggle}
          style={{
            paddingHorizontal: 10,
            paddingVertical: 3,
            borderRadius: 999,
            backgroundColor: active ? `${palette.accentColor}28` : pillBgOff,
            borderWidth: 1,
            borderColor: active ? `${palette.accentColor}60` : pillBorderOff,
          }}
        >
          <Text
            style={{
              color: active
                ? palette.accentColor
                : isDark
                  ? "#64748b"
                  : "#94a3b8",
              fontSize: 10,
              fontWeight: "700",
            }}
          >
            {active ? "ON" : "OFF"}
          </Text>
        </Pressable>
      </View>

      {/* Gradient bar */}
      <View
        style={{
          height: 10,
          borderRadius: 999,
          marginBottom: 6,
          opacity: active ? 1 : 0.3,
          ...({ backgroundImage: palette.gradient } as any),
        }}
      />

      {/* Tick labels */}
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        {["Low", "Moderate", "High", "Extreme"].map((label, i) => (
          <Text
            key={label}
            style={{
              color:
                i < 2
                  ? tickDim
                  : i === 2
                    ? tickMid
                    : active
                      ? palette.accentColor
                      : tickDim,
              fontSize: 10,
              fontWeight: i >= 2 ? "700" : "400",
            }}
          >
            {label}
          </Text>
        ))}
      </View>
    </>
  );
}
