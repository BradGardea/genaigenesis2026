import { AppTheme } from "../types/theme";

export const URGENCY_LEVELS = [
  "notification",
  "caution",
  "warning",
  "urgent warning",
  "alert",
  "urgent alert",
  "extreme urgency alert"
] as const;

export type UrgencyLevel = (typeof URGENCY_LEVELS)[number];

export type InfoCategory =
  | "evacuation"
  | "closure"
  | "traffic"
  | "family notification"
  | "shelter"
  | "hazard update"
  | "general";

export interface InfoBubble {
  id: string;
  title: string;
  details: string;
  urgency: UrgencyLevel;
  category: InfoCategory;
  occurredAt: string;
  updatedAt: string;
  area: string;
  source: string;
}

export interface EvacuationPlan {
  id: string;
  title: string;
  successProbability: number;
  summary: string;
  steps: string[];
  packingList: string[];
  updatedAt?: string;
}

export type ConnectionRelationship = "dependent" | "guardian" | "friend" | "acquaintance";

export interface UserConnection {
  id: string;
  ownerPhone: string;
  contactPhone: string;
  relationship: ConnectionRelationship;
  trustLevel: number;
  updatedAt: string;
}

export interface ConnectionCreatePayload {
  ownerPhone: string;
  contactPhone: string;
  relationship: ConnectionRelationship;
}

export interface SavedInformation {
  id: string;
  title: string;
  note: string;
  updatedAt: string;
}

export interface WeatherUpdate {
  id: string;
  headline: string;
  details: string;
  severity: string;
  updatedAt: string;
  rawData?: Record<string, unknown>;
}

export interface WeatherDatasetMetadata {
  dataset_name: string;
  version: string;
  generated_at: string;
  scenario_note: string;
  location: Record<string, unknown>;
  schema_alignment: Record<string, unknown>;
}

export interface WeatherStepMeta {
  step_index: number;
  step_time: string;
  total_steps: number;
  has_next: boolean;
  next_step_index: number | null;
}

export interface WeatherStepResponse {
  metadata: WeatherDatasetMetadata;
  step: WeatherStepMeta;
  beautified: WeatherUpdate[];
  raw: Record<string, unknown>;
}

export interface MapIncidentPoint {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  urgency: UrgencyLevel;
  category: InfoCategory;
  updatedAt: string;
}

export interface UserProfileDraft {
  fullName: string;
  phoneNumber: string;
  homeArea: string;
}

export interface UrgencyCardColorSet {
  backgroundColor: string;
  borderColor: string;
}

export const URGENCY_WEIGHT: Record<UrgencyLevel, number> = {
  notification: 1,
  caution: 2,
  warning: 3,
  "urgent warning": 4,
  alert: 5,
  "urgent alert": 6,
  "extreme urgency alert": 7
};

export const URGENCY_CARD_COLORS: Record<
  UrgencyLevel,
  Record<AppTheme, UrgencyCardColorSet>
> = {
  notification: {
    light: { backgroundColor: "#e0f2fe", borderColor: "#7dd3fc" },
    dark: { backgroundColor: "#0c4a6e", borderColor: "#38bdf8" }
  },
  caution: {
    light: { backgroundColor: "#fef9c3", borderColor: "#facc15" },
    dark: { backgroundColor: "#713f12", borderColor: "#facc15" }
  },
  warning: {
    light: { backgroundColor: "#ffedd5", borderColor: "#fb923c" },
    dark: { backgroundColor: "#7c2d12", borderColor: "#fb923c" }
  },
  "urgent warning": {
    light: { backgroundColor: "#fed7aa", borderColor: "#f97316" },
    dark: { backgroundColor: "#9a3412", borderColor: "#f97316" }
  },
  alert: {
    light: { backgroundColor: "#fee2e2", borderColor: "#ef4444" },
    dark: { backgroundColor: "#7f1d1d", borderColor: "#f87171" }
  },
  "urgent alert": {
    light: { backgroundColor: "#fecaca", borderColor: "#dc2626" },
    dark: { backgroundColor: "#991b1b", borderColor: "#f87171" }
  },
  "extreme urgency alert": {
    light: { backgroundColor: "#fca5a5", borderColor: "#b91c1c" },
    dark: { backgroundColor: "#450a0a", borderColor: "#ef4444" }
  }
};
