import { MapIncidentPoint } from "../types";

export const mapIncidentPointsMock: MapIncidentPoint[] = [
  {
    id: "map-001",
    label: "Zone C Evacuation Perimeter",
    latitude: 43.706,
    longitude: -79.41,
    urgency: "extreme urgency alert",
    category: "evacuation",
    updatedAt: "2026-03-13T16:30:00Z"
  },
  {
    id: "map-002",
    label: "Highway 14 Bridge Closure",
    latitude: 43.712,
    longitude: -79.388,
    urgency: "urgent alert",
    category: "closure",
    updatedAt: "2026-03-13T16:05:00Z"
  }
];
