export type Severity = "low" | "medium" | "high" | "critical";

export interface RiskSignal {
  id: string;
  name: string;
  value: string;
  severity: Severity;
  source: string;
}

export interface EmergencyEvent {
  id: string;
  title: string;
  location: string;
  severity: Severity;
  detectedAt: string;
  source: string;
}

export interface EvacuationProfile {
  familySize: number;
  vehicles: number;
  hasChildren: boolean;
  hasElderly: boolean;
  hasMobilityNeeds: boolean;
}

export interface Coordinate {
  lng: number;
  lat: number;
}

export interface HazardReport {
  hazard_type: string;
  location: Coordinate;
  radius_meters?: number;
  description?: string;
}

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface GeoJSONLineString {
  type: "LineString";
  coordinates: number[][];
}

export interface HazardZone {
  hazard_id: string;
  polygon: GeoJSONPolygon;
  hazard_type: string;
  severity: string;
  radius_meters: number;
  description?: string;
  reported_at?: string;
}

export interface RouteRequest {
  origin: Coordinate;
  destination: Coordinate;
  profile?: EvacuationProfileInput;
}

export interface EvacuationProfileInput {
  family_size?: number;
  vehicles?: number;
  has_children?: boolean;
  has_elderly?: boolean;
  has_mobility_needs?: boolean;
}

export interface RouteResponse {
  route_id: string;
  geometry: GeoJSONLineString;
  distance_meters: number;
  duration_seconds: number;
  waypoints: Coordinate[];
  hazards_avoided: string[];
  instructions: string[];
  segment_durations?: number[];
  backup_route: GeoJSONLineString | null;
}

export interface RouteWeatherPoint {
  lng: number;
  lat: number;
  temperature_c: number | null;
  wind_speed_kmh: number | null;
  precipitation_probability: number | null;
  relative_humidity: number | null;
}

export interface WeatherAlertFeature {
  type: "Feature";
  geometry: GeoJSONPolygon | null;
  properties: {
    id: string;
    event: string;
    severity: string;
    region: string;
  };
}

export interface WeatherAlertCollection {
  type: "FeatureCollection";
  features: WeatherAlertFeature[];
}

