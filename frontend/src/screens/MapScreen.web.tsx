import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Pressable, Text, TextInput, View } from "react-native";
import { mapIncidentPointsMock } from "../data";
import { AppTheme } from "../types/theme";
import { Coordinate, GeoJSONLineString, HazardZone } from "../types/domain";
import { useEvacuationRoute } from "../hooks/useEvacuationRoute";
import { getActiveHazards } from "../services/api";
import { ReportHazardModal } from "../components/ReportHazardModal";

interface MapScreenProps {
  theme: AppTheme;
}

const MAPBOX_PUBLIC_TOKEN = process.env.EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "";

const ROUTE_SOURCE = "evacuation-route";
const ROUTE_LAYER = "evacuation-route-line";
const HAZARD_SOURCE = "hazard-zones";
const HAZARD_FILL_LAYER = "hazard-zones-fill";
const HAZARD_OUTLINE_LAYER = "hazard-zones-outline";

const DEFAULT_CENTER: [number, number] = [-79.41, 43.706];

function coordFromText(text: string): Coordinate | null {
  const parts = text.split(",").map((s) => s.trim());
  if (parts.length !== 2) return null;
  const lat = parseFloat(parts[0]);
  const lng = parseFloat(parts[1]);
  if (isNaN(lat) || isNaN(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return { lat, lng };
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

export function MapScreen({ theme }: MapScreenProps) {
  const isDark = theme === "dark";
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const originMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const destMarkerRef = useRef<mapboxgl.Marker | null>(null);

  const [originText, setOriginText] = useState("");
  const [destText, setDestText] = useState("");
  const [origin, setOrigin] = useState<Coordinate | null>(null);
  const [destination, setDestination] = useState<Coordinate | null>(null);
  const [hazardZones, setHazardZones] = useState<HazardZone[]>([]);
  const [hazardModalVisible, setHazardModalVisible] = useState(false);
  const [mapClickMode, setMapClickMode] = useState<"origin" | "destination" | null>(null);

  const { route, loading, error, rerouting, refetch } = useEvacuationRoute(origin, destination);

  const initialPoint = useMemo(
    () =>
      mapIncidentPointsMock[0] ?? {
        latitude: DEFAULT_CENTER[1],
        longitude: DEFAULT_CENTER[0],
        label: "Default",
      },
    []
  );

  const fetchHazards = useCallback(async () => {
    try {
      const zones = await getActiveHazards();
      setHazardZones(zones);
    } catch {
      // non-critical — hazards just won't render
    }
  }, []);

  useEffect(() => {
    fetchHazards();
    const interval = setInterval(fetchHazards, 10_000);
    return () => clearInterval(interval);
  }, [fetchHazards]);

  // ── Map init ──────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !MAPBOX_PUBLIC_TOKEN) return;

    mapboxgl.accessToken = MAPBOX_PUBLIC_TOKEN;

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: isDark ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12",
      center: [initialPoint.longitude, initialPoint.latitude],
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
      // Route source + layer
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
        },
      });

      // Hazard source + layers
      map.addSource(HAZARD_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: HAZARD_FILL_LAYER,
        type: "fill",
        source: HAZARD_SOURCE,
        paint: {
          "fill-color": "#ef4444",
          "fill-opacity": 0.25,
        },
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
    });

    // Incident markers
    const markers: mapboxgl.Marker[] = [];
    mapIncidentPointsMock.forEach((point) => {
      const marker = new mapboxgl.Marker({ color: "#dc2626" }).setLngLat([
        point.longitude,
        point.latitude,
      ]);
      const popup = new mapboxgl.Popup({ offset: 24 }).setHTML(
        `<strong>${point.label}</strong><br/>Urgency: ${point.urgency}`
      );
      marker.setPopup(popup).addTo(map);
      markers.push(marker);
    });
    markersRef.current = markers;

    // Click-to-set origin/destination
    map.on("click", (e) => {
      const coord: Coordinate = { lng: e.lngLat.lng, lat: e.lngLat.lat };
      const label = `${coord.lat.toFixed(5)}, ${coord.lng.toFixed(5)}`;
      const event = new CustomEvent("map-click", { detail: { coord, label } });
      window.dispatchEvent(event);
    });

    mapRef.current = map;

    return () => {
      markers.forEach((m) => m.remove());
      map.remove();
      mapRef.current = null;
    };
  }, [initialPoint.latitude, initialPoint.longitude, isDark]);

  // Listen for map clicks to set origin / destination
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
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(ROUTE_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    if (route?.geometry) {
      source.setData({
        type: "Feature",
        properties: {},
        geometry: route.geometry,
      });

      const coords = (route.geometry as GeoJSONLineString).coordinates as [number, number][];
      if (coords.length > 1) {
        const bounds = coords.reduce(
          (b, c) => b.extend(c as mapboxgl.LngLatLike),
          new mapboxgl.LngLatBounds(coords[0], coords[0])
        );
        map.fitBounds(bounds, { padding: 80, duration: 800 });
      }
    } else {
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }, [route]);

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

  // ── Update hazard polygons ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(HAZARD_SOURCE) as mapboxgl.GeoJSONSource | undefined;
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
        setOriginText(`${coord.lat.toFixed(5)}, ${coord.lng.toFixed(5)}`);
      },
      () => {
        // fall back to default
      }
    );
  };

  const mapCenter: Coordinate | null = origin ?? destination ?? null;

  return (
    <View className={`flex-1 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      {/* ── Rerouting banner ────────────────────────────── */}
      {rerouting && (
        <View className="z-10 bg-amber-500 px-4 py-2">
          <Text className="text-center text-sm font-semibold text-black">
            ⚠ Rerouting — new hazard detected on your path…
          </Text>
        </View>
      )}

      <View className="flex-1 flex-row">
        {/* ── Sidebar panel ─────────────────────────────── */}
        <View
          className={`w-80 border-r p-4 ${
            isDark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-white"
          }`}
          style={{ minWidth: 320 }}
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
            />
            <Pressable
              onPress={() => setMapClickMode(mapClickMode === "origin" ? null : "origin")}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "origin" ? "bg-green-600" : isDark ? "bg-slate-700" : "bg-slate-200"
              }`}
            >
              <Text className={`text-xs ${mapClickMode === "origin" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}>
                📍
              </Text>
            </Pressable>
          </View>
          <Pressable onPress={handleUseCurrentLocation} className="mb-3">
            <Text className="text-xs text-blue-500">Use current location</Text>
          </Pressable>

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
            />
            <Pressable
              onPress={() => setMapClickMode(mapClickMode === "destination" ? null : "destination")}
              className={`rounded-lg px-2 py-2 ${
                mapClickMode === "destination" ? "bg-purple-600" : isDark ? "bg-slate-700" : "bg-slate-200"
              }`}
            >
              <Text className={`text-xs ${mapClickMode === "destination" ? "text-white" : isDark ? "text-slate-300" : "text-slate-600"}`}>
                🏁
              </Text>
            </Pressable>
          </View>

          {mapClickMode && (
            <Text className="mb-2 text-xs text-amber-500">
              Click the map to set {mapClickMode}
            </Text>
          )}

          <Pressable
            onPress={handlePlanRoute}
            disabled={loading}
            className={`mb-4 rounded-lg py-3 ${loading ? "bg-blue-400" : "bg-blue-600"}`}
          >
            <Text className="text-center text-sm font-semibold text-white">
              {loading ? "Planning…" : "Plan Route"}
            </Text>
          </Pressable>

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
                      +{route.instructions.length - 6} more…
                    </Text>
                  )}
                </View>
              )}
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
            className={`rounded-lg py-3 ${isDark ? "bg-red-700" : "bg-red-600"}`}
          >
            <Text className="text-center text-sm font-semibold text-white">
              Report Hazard
            </Text>
          </Pressable>
        </View>

        {/* ── Map container ─────────────────────────────── */}
        <View className="flex-1">
          {MAPBOX_PUBLIC_TOKEN ? (
            <div ref={containerRef} style={{ width: "100%", height: "100%", cursor: mapClickMode ? "crosshair" : undefined }} />
          ) : (
            <View
              className={`flex-1 items-center justify-center px-4 ${
                isDark ? "bg-slate-800" : "bg-slate-50"
              }`}
            >
              <Text className={`text-center text-sm ${isDark ? "text-slate-300" : "text-slate-600"}`}>
                Mapbox token not set. Add EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN in frontend/.env.
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
