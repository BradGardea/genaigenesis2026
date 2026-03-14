import { useEffect, useMemo, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Text, View } from "react-native";
import { mapIncidentPointsMock } from "../data";
import { AppTheme } from "../types/theme";

interface MapScreenProps {
  theme: AppTheme;
}

const MAPBOX_PUBLIC_TOKEN = process.env.EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "";

export function MapScreen({ theme }: MapScreenProps) {
  const isDark = theme === "dark";
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  const initialPoint = useMemo(
    () =>
      mapIncidentPointsMock[0] ?? {
        latitude: 43.706,
        longitude: -79.41,
        label: "Default point"
      },
    []
  );

  useEffect(() => {
    if (!containerRef.current || !MAPBOX_PUBLIC_TOKEN) {
      return;
    }

    mapboxgl.accessToken = MAPBOX_PUBLIC_TOKEN;

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: isDark ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12",
      center: [initialPoint.longitude, initialPoint.latitude],
      zoom: 10
    });

    map.addControl(new mapboxgl.NavigationControl(), "top-right");

    mapIncidentPointsMock.forEach((point) => {
      const marker = new mapboxgl.Marker({ color: "#dc2626" }).setLngLat([
        point.longitude,
        point.latitude
      ]);

      const popup = new mapboxgl.Popup({ offset: 24 }).setHTML(
        `<strong>${point.label}</strong><br/>Urgency: ${point.urgency}`
      );

      marker.setPopup(popup).addTo(map);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [initialPoint.latitude, initialPoint.longitude, isDark]);

  return (
    <View className={`flex-1 px-4 pt-3 ${isDark ? "bg-slate-950" : "bg-slate-100"}`}>
      <Text className={`text-sm ${isDark ? "text-slate-400" : "text-slate-600"}`}>
        Web Mapbox view with live controls and incident markers.
      </Text>

      <View
        className={`mt-3 flex-1 overflow-hidden rounded-2xl border p-2 ${
          isDark ? "border-slate-700 bg-slate-900" : "border-slate-300 bg-white"
        }`}
      >
        {MAPBOX_PUBLIC_TOKEN ? (
          <div ref={containerRef} style={{ width: "100%", height: "100%", borderRadius: 12 }} />
        ) : (
          <View
            className={`flex-1 items-center justify-center rounded-xl border border-dashed px-4 ${
              isDark ? "border-slate-600 bg-slate-800" : "border-slate-300 bg-slate-50"
            }`}
          >
            <Text className={`text-center text-sm ${isDark ? "text-slate-300" : "text-slate-600"}`}>
              Mapbox token not set. Add EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN in frontend/.env.
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}
