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

