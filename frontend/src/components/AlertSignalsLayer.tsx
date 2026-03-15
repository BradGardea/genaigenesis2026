/**
 * AlertSignalsLayer
 *
 * Fetches live disaster signals from /api/v1/alerts/signals and renders
 * them as per-category heatmap layers on the Mapbox map.
 *
 * This component is fully independent of the disaster demo stepping —
 * it does not read or write DisasterDemoContext.
 */
import { useEffect, useRef } from "react";
import { fetchAlertSignals, AlertSignalFeature } from "../services/api";

// ── Layer / source identifiers (must not collide with demo layer IDs) ─────────
const SOURCE_ID = "alert-signals-source";

const LAYER_IDS = {
  earthquake: "alert-signals-earthquake",
  fire:       "alert-signals-fire",
  storm:      "alert-signals-storm",
  flood:      "alert-signals-flood",
  general:    "alert-signals-general",
} as const;

type Category = keyof typeof LAYER_IDS;

// ── Heatmap color configs per category ───────────────────────────────────────
const CATEGORY_COLORS: Record<Category, unknown[]> = {
  earthquake: [
    "interpolate", ["linear"], ["heatmap-density"],
    0,    "rgba(0,0,0,0)",
    0.15, "rgba(180,120,255,0.55)",
    0.35, "rgba(140,80,255,0.8)",
    0.55, "rgba(100,40,200,0.9)",
    0.75, "rgba(60,0,140,1)",
    1.0,  "rgba(20,0,80,1)",
  ],
  fire: [
    "interpolate", ["linear"], ["heatmap-density"],
    0,    "rgba(0,0,0,0)",
    0.15, "rgba(255,255,120,0.55)",
    0.35, "rgba(255,200,0,0.8)",
    0.55, "rgba(255,120,0,0.9)",
    0.75, "rgba(200,40,0,1)",
    1.0,  "rgba(120,0,0,1)",
  ],
  storm: [
    "interpolate", ["linear"], ["heatmap-density"],
    0,    "rgba(0,0,0,0)",
    0.15, "rgba(43,95,184,0.55)",
    0.35, "rgba(34,184,200,0.8)",
    0.55, "rgba(80,210,220,0.9)",
    0.75, "rgba(255,230,50,1)",
    1.0,  "rgba(255,255,255,1)",
  ],
  flood: [
    "interpolate", ["linear"], ["heatmap-density"],
    0,    "rgba(0,0,0,0)",
    0.15, "rgba(8,48,107,0.55)",
    0.35, "rgba(8,81,156,0.8)",
    0.55, "rgba(33,113,181,0.9)",
    0.75, "rgba(66,146,198,1)",
    1.0,  "rgba(198,219,239,1)",
  ],
  general: [
    "interpolate", ["linear"], ["heatmap-density"],
    0,    "rgba(0,0,0,0)",
    0.15, "rgba(103,169,207,0.55)",
    0.35, "rgba(209,229,240,0.8)",
    0.55, "rgba(253,219,199,0.9)",
    0.75, "rgba(239,138,98,1)",
    1.0,  "rgba(178,24,43,1)",
  ],
};

// Heatmap radius expressions per category (larger for area-based events)
const CATEGORY_RADIUS: Record<Category, unknown[]> = {
  earthquake: ["interpolate", ["linear"], ["zoom"], 0, 4,  5, 14, 9, 28],
  fire:       ["interpolate", ["linear"], ["zoom"], 0, 5,  5, 18, 9, 40],
  storm:      ["interpolate", ["linear"], ["zoom"], 0, 8,  5, 28, 9, 60],
  flood:      ["interpolate", ["linear"], ["zoom"], 0, 7,  5, 22, 9, 48],
  general:    ["interpolate", ["linear"], ["zoom"], 0, 5,  5, 16, 9, 32],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function categorize(signalType: string): Category {
  const t = (signalType ?? "").toLowerCase();
  if (t.includes("earthquake") || t.includes("seismic") || t.includes("quake")) return "earthquake";
  if (t.includes("fire") || t.includes("wildfire")) return "fire";
  if (
    t.includes("storm") || t.includes("hurricane") ||
    t.includes("cyclone") || t.includes("typhoon") || t.includes("tropical")
  ) return "storm";
  if (t.includes("flood")) return "flood";
  return "general";
}

function severityToWeight(severity: string): number {
  switch ((severity ?? "").toLowerCase()) {
    case "extreme": return 1.0;
    case "high":    return 0.75;
    case "moderate":return 0.5;
    case "low":     return 0.25;
    default:        return 0.45;
  }
}

/** Box-Muller normal sample */
function randn(): number {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Spread in degrees for each category's scatter cloud
const SCATTER_RADIUS_DEG: Record<Category, number> = {
  earthquake: 0.08,
  fire:       0.05,
  storm:      0.45,
  flood:      0.12,
  general:    0.15,
};
const SCATTER_COUNT: Record<Category, number> = {
  earthquake: 35,
  fire:       30,
  storm:      55,
  flood:      45,
  general:    30,
};

interface GeoJSONPoint {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: { weight: number; category: Category };
}

function signalsToGeoJSON(features: AlertSignalFeature[]): {
  type: "FeatureCollection";
  features: GeoJSONPoint[];
} {
  const pts: GeoJSONPoint[] = [];

  for (const feat of features) {
    const p = feat.properties;
    const lat = p.latitude;
    const lon = p.longitude;
    if (lat == null || lon == null) continue;

    const category = categorize(p.signal_type);
    const baseWeight = severityToWeight(p.severity);
    const radius = SCATTER_RADIUS_DEG[category];
    const count  = SCATTER_COUNT[category];

    for (let i = 0; i < count; i++) {
      pts.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [
            lon + randn() * radius,
            lat + randn() * radius,
          ],
        },
        properties: {
          weight: Math.min(1, baseWeight * (0.75 + Math.random() * 0.25)),
          category,
        },
      });
    }
  }

  return { type: "FeatureCollection", features: pts };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface AlertSignalsLayerProps {
  map: any;
  mapLoaded: boolean;
}

export function AlertSignalsLayer({ map, mapLoaded }: AlertSignalsLayerProps) {
  const dataRef = useRef<{ type: "FeatureCollection"; features: GeoJSONPoint[] }>({
    type: "FeatureCollection",
    features: [],
  });

  // ── Setup Mapbox source + layers once map is ready ────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;

    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: dataRef.current,
      });
    }

    for (const [cat, layerId] of Object.entries(LAYER_IDS) as [Category, string][]) {
      if (!map.getLayer(layerId)) {
        map.addLayer({
          id: layerId,
          type: "heatmap",
          source: SOURCE_ID,
          filter: ["==", ["get", "category"], cat],
          paint: {
            "heatmap-weight":    ["interpolate", ["linear"], ["get", "weight"], 0, 0, 1, 1],
            "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 2.5],
            "heatmap-radius":    CATEGORY_RADIUS[cat],
            "heatmap-opacity":   0.72,
            "heatmap-color":     CATEGORY_COLORS[cat],
          },
        });
      }
    }

    return () => {
      try {
        for (const layerId of Object.values(LAYER_IDS)) {
          if (map.getLayer(layerId)) map.removeLayer(layerId);
        }
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch { /* map destroyed */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, mapLoaded]);

  // ── Fetch signals and update source data ─────────────────────────────────
  useEffect(() => {
    if (!map || !mapLoaded) return;

    async function load() {
      try {
        const collection = await fetchAlertSignals();
        const geoJSON = signalsToGeoJSON(collection.features);
        dataRef.current = geoJSON;
        (map.getSource(SOURCE_ID) as any)?.setData(geoJSON);
      } catch {
        // non-critical — partial data or backend unavailable
      }
    }

    load();
    const interval = setInterval(load, 5 * 60 * 1000); // refresh every 5 min
    return () => clearInterval(interval);
  }, [map, mapLoaded]);

  // This component only manages Mapbox layers — no visible React UI
  return null;
}
