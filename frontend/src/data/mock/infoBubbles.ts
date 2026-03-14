import { InfoBubble } from "../types";

export const infoBubblesMock: InfoBubble[] = [
  {
    id: "inf-001",
    title: "Mandatory evacuation expanded for river corridor",
    details:
      "Residents within Zone C must leave before 18:30 local time due to rapid flood rise.",
    urgency: "extreme urgency alert",
    category: "evacuation",
    occurredAt: "2026-03-13T16:10:00Z",
    updatedAt: "2026-03-13T16:30:00Z",
    area: "River Corridor - Zone C",
    source: "Regional Emergency Management"
  },
  {
    id: "inf-002",
    title: "Bridge closure on Highway 14",
    details: "Northbound access is closed. Use East Ridge detour until further notice.",
    urgency: "urgent alert",
    category: "closure",
    occurredAt: "2026-03-13T15:45:00Z",
    updatedAt: "2026-03-13T16:05:00Z",
    area: "Highway 14",
    source: "Transportation Operations Center"
  },
  {
    id: "inf-003",
    title: "Traffic congestion near shelter intake",
    details: "Expect 25-40 minute delays around Civic Arena access roads.",
    urgency: "warning",
    category: "traffic",
    occurredAt: "2026-03-13T15:40:00Z",
    updatedAt: "2026-03-13T15:50:00Z",
    area: "Civic Arena",
    source: "Traffic Camera Feed"
  },
  {
    id: "inf-004",
    title: "Family reunification line active",
    details: "Use hotline 1-800-555-0192 for family member status checks.",
    urgency: "notification",
    category: "family notification",
    occurredAt: "2026-03-13T14:30:00Z",
    updatedAt: "2026-03-13T15:00:00Z",
    area: "County Wide",
    source: "Public Information Office"
  },
  {
    id: "inf-005",
    title: "Wind gusts expected to intensify by evening",
    details: "Conditions may worsen wildfire spread in exposed hillside sectors.",
    urgency: "urgent warning",
    category: "hazard update",
    occurredAt: "2026-03-13T16:00:00Z",
    updatedAt: "2026-03-13T16:20:00Z",
    area: "Hillside Sectors",
    source: "National Weather Service"
  },
  {
    id: "inf-006",
    title: "Additional shelter now accepting arrivals",
    details: "Westside High School gym opened with medical and pet support.",
    urgency: "caution",
    category: "shelter",
    occurredAt: "2026-03-13T15:20:00Z",
    updatedAt: "2026-03-13T15:35:00Z",
    area: "Westside District",
    source: "Shelter Coordination Team"
  },
  {
    id: "inf-007",
    title: "Air quality advisory for smoke exposure",
    details: "N95 masks recommended outdoors; limit activity for children and seniors.",
    urgency: "alert",
    category: "general",
    occurredAt: "2026-03-13T15:55:00Z",
    updatedAt: "2026-03-13T16:15:00Z",
    area: "Metro Area",
    source: "Public Health Unit"
  }
];
