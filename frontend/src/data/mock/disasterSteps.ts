import {
  EvacuationPlan,
  InfoBubble,
  SavedInformation,
  UserConnection,
  WeatherUpdate
} from "../types";

export interface DisasterStepUpdateSummary {
  alerts: number;
  evacuationPlans: number;
  connections: number;
  savedInformation: number;
  weather: number;
}

export interface DisasterStepSectionUpdatedAt {
  alerts: string;
  evacuationPlans: string;
  connections: string;
  savedInformation: string;
  weather: string;
}

export interface DisasterStepData {
  id: string;
  simulatedAt: string;
  alerts: InfoBubble[];
  evacuationPlans: EvacuationPlan[];
  connections: UserConnection[];
  savedInformation: SavedInformation[];
  weather: WeatherUpdate[];
  cityStateRaw?: Record<string, unknown>;
  cityStateBeautified?: Record<string, unknown>[];
  sectionUpdatedAt: DisasterStepSectionUpdatedAt;
  updateSummary: DisasterStepUpdateSummary;
}

function at(minuteOffset: number): string {
  const base = new Date("2026-03-13T16:00:00Z");
  base.setMinutes(base.getMinutes() + minuteOffset);
  return base.toISOString();
}

export const DISASTER_STEP_INTERVAL_MINUTES = 10;

export const disasterStepsMock: DisasterStepData[] = [
  {
    id: "step-1",
    simulatedAt: at(0),
    alerts: [
      {
        id: "inf-001",
        title: "Flood warning active along River Corridor",
        details: "Residents in Zone B should prepare to evacuate and monitor official channels.",
        urgency: "warning",
        category: "evacuation",
        occurredAt: at(-5),
        updatedAt: at(0),
        area: "River Corridor - Zone B",
        source: "Regional Emergency Management"
      },
      {
        id: "inf-002",
        title: "Bridge traffic slowdowns on Highway 14",
        details: "Expect reduced speed due to debris checks and lane control operations.",
        urgency: "caution",
        category: "traffic",
        occurredAt: at(-7),
        updatedAt: at(0),
        area: "Highway 14",
        source: "Transportation Operations Center"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Primary Route: Southbound via Cedar Loop",
        successProbability: 72,
        summary: "Leave before route congestion peaks and regroup at Civic Arena intake.",
        steps: [
          "Pack essentials for 12 hours.",
          "Depart using Cedar Loop southbound.",
          "Check in at Civic Arena gate C."
        ],
        packingList: ["ID and medication", "Phone charger", "Water and masks"],
        updatedAt: at(0)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "416-555-0142",
        contactPhone: "416-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(0)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Shelter Intake Address",
        note: "Civic Arena, 255 Front Street, Entrance C.",
        updatedAt: at(0)
      }
    ],
    weather: [
      {
        id: "weather-001",
        headline: "Heavy rainfall continues",
        details: "Rainfall rates remain elevated, with runoff increasing near low-lying roads.",
        severity: "moderate",
        updatedAt: at(0)
      }
    ],
    sectionUpdatedAt: {
      alerts: at(0),
      evacuationPlans: at(0),
      connections: at(0),
      savedInformation: at(0),
      weather: at(0)
    },
    updateSummary: {
      alerts: 0,
      evacuationPlans: 0,
      connections: 0,
      savedInformation: 0,
      weather: 0
    }
  },
  {
    id: "step-2",
    simulatedAt: at(10),
    alerts: [
      {
        id: "inf-001",
        title: "Mandatory evacuation issued for River Corridor Zone C",
        details: "Residents in Zone C must leave before 18:30 local time due to rapid flood rise.",
        urgency: "extreme urgency alert",
        category: "evacuation",
        occurredAt: at(6),
        updatedAt: at(10),
        area: "River Corridor - Zone C",
        source: "Regional Emergency Management"
      },
      {
        id: "inf-002",
        title: "Bridge closure on Highway 14",
        details: "Northbound access is now closed. Use East Ridge detour until further notice.",
        urgency: "urgent alert",
        category: "closure",
        occurredAt: at(8),
        updatedAt: at(10),
        area: "Highway 14",
        source: "Transportation Operations Center"
      },
      {
        id: "inf-003",
        title: "Family reunification line active",
        details: "Use hotline 1-800-555-0192 for family member status checks.",
        urgency: "notification",
        category: "family notification",
        occurredAt: at(9),
        updatedAt: at(10),
        area: "County Wide",
        source: "Public Information Office"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Primary Route: Southbound via Cedar Loop",
        successProbability: 78,
        summary: "Move now before bridge closure spillover increases downtown congestion.",
        steps: [
          "Notify your emergency contact.",
          "Depart using Cedar Loop southbound.",
          "Proceed to Civic Arena gate C."
        ],
        packingList: ["Medication", "Water", "Phone and charger", "Documents"],
        updatedAt: at(10)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "416-555-0142",
        contactPhone: "416-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(10)
      },
      {
        id: "conn-002",
        ownerPhone: "416-555-0142",
        contactPhone: "647-555-0126",
        relationship: "friend",
        trustLevel: 3,
        updatedAt: at(10)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Shelter Intake Address",
        note: "Civic Arena, 255 Front Street, Entrance C.",
        updatedAt: at(0)
      },
      {
        id: "save-002",
        title: "Detour Route",
        note: "Use East Ridge -> Oakway -> South Cedar Loop.",
        updatedAt: at(10)
      }
    ],
    weather: [
      {
        id: "weather-001",
        headline: "Heavy rainfall intensifying",
        details: "Localized flash flooding is likely in river-adjacent streets in the next hour.",
        severity: "high",
        updatedAt: at(10)
      }
    ],
    sectionUpdatedAt: {
      alerts: at(10),
      evacuationPlans: at(10),
      connections: at(10),
      savedInformation: at(10),
      weather: at(10)
    },
    updateSummary: {
      alerts: 3,
      evacuationPlans: 1,
      connections: 2,
      savedInformation: 1,
      weather: 1
    }
  },
  {
    id: "step-3",
    simulatedAt: at(20),
    alerts: [
      {
        id: "inf-001",
        title: "Evacuation expanded to Zone D",
        details: "Zone D now under urgent evacuation as water levels exceed projected thresholds.",
        urgency: "urgent alert",
        category: "evacuation",
        occurredAt: at(18),
        updatedAt: at(20),
        area: "River Corridor - Zone D",
        source: "Regional Emergency Management"
      },
      {
        id: "inf-004",
        title: "Secondary shelter opened at Westside High",
        details: "Westside High gym now accepting arrivals with medical and pet support.",
        urgency: "caution",
        category: "shelter",
        occurredAt: at(19),
        updatedAt: at(20),
        area: "Westside District",
        source: "Shelter Coordination Team"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Primary Route: Southbound via Cedar Loop",
        successProbability: 69,
        summary: "Congestion is building; switch to staggered departure by household group.",
        steps: [
          "Wait for your zone release call.",
          "Use Oakway connector to avoid closure backlog.",
          "Check in at assigned shelter desk."
        ],
        packingList: ["Medication", "ID", "Phone charger", "Warm layer"],
        updatedAt: at(20)
      },
      {
        id: "plan-002",
        title: "Alternate Route: Westside Intake",
        successProbability: 74,
        summary: "For western neighborhoods, Westside High has shorter intake time.",
        steps: [
          "Head west via Parkline Road.",
          "Avoid Highway 14 entirely.",
          "Follow volunteer marshals at Westside High."
        ],
        packingList: ["Essential documents", "Water", "Masks"],
        updatedAt: at(20)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "416-555-0142",
        contactPhone: "416-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(20)
      },
      {
        id: "conn-002",
        ownerPhone: "416-555-0142",
        contactPhone: "647-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(20)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Shelter Intake Address",
        note: "Civic Arena, 255 Front Street, Entrance C.",
        updatedAt: at(0)
      },
      {
        id: "save-002",
        title: "Detour Route",
        note: "Use East Ridge -> Oakway -> South Cedar Loop.",
        updatedAt: at(10)
      },
      {
        id: "save-003",
        title: "Westside High Shelter",
        note: "188 King St. W. Bring pet carriers if possible.",
        updatedAt: at(20)
      }
    ],
    weather: [
      {
        id: "weather-001",
        headline: "Rain tapering, runoff still high",
        details: "Rainfall starts to ease but runoff keeps flood risk elevated in low areas.",
        severity: "high",
        updatedAt: at(20)
      },
      {
        id: "weather-002",
        headline: "Wind gust advisory",
        details: "Gusts up to 60 km/h expected for exposed corridors.",
        severity: "moderate",
        updatedAt: at(20)
      }
    ],
    sectionUpdatedAt: {
      alerts: at(20),
      evacuationPlans: at(20),
      connections: at(20),
      savedInformation: at(20),
      weather: at(20)
    },
    updateSummary: {
      alerts: 2,
      evacuationPlans: 2,
      connections: 2,
      savedInformation: 1,
      weather: 2
    }
  },
  {
    id: "step-4",
    simulatedAt: at(30),
    alerts: [
      {
        id: "inf-005",
        title: "Air quality advisory for smoke and debris",
        details: "N95 masks recommended outdoors; reduce exposure for children and seniors.",
        urgency: "alert",
        category: "general",
        occurredAt: at(28),
        updatedAt: at(30),
        area: "Metro Area",
        source: "Public Health Unit"
      },
      {
        id: "inf-006",
        title: "Traffic delay near Civic Arena intake",
        details: "Expect 25-40 minute delays on intake roads due to rerouted bridge traffic.",
        urgency: "warning",
        category: "traffic",
        occurredAt: at(29),
        updatedAt: at(30),
        area: "Civic Arena",
        source: "Traffic Camera Feed"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-002",
        title: "Alternate Route: Westside Intake",
        successProbability: 81,
        summary: "Westside intake is now the fastest option for most active zones.",
        steps: [
          "Travel via Parkline Road.",
          "Avoid Civic Arena approaches unless instructed.",
          "Use triage desk at Westside High entrance."
        ],
        packingList: ["Medication", "Water", "Documents", "Phone charger"],
        updatedAt: at(30)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "416-555-0142",
        contactPhone: "416-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(30)
      },
      {
        id: "conn-002",
        ownerPhone: "416-555-0142",
        contactPhone: "647-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(30)
      },
      {
        id: "conn-003",
        ownerPhone: "416-555-0142",
        contactPhone: "437-555-0188",
        relationship: "dependent",
        trustLevel: 5,
        updatedAt: at(30)
      }
    ],
    savedInformation: [
      {
        id: "save-004",
        title: "Family Reunification Hotline",
        note: "Call 1-800-555-0192 with household code if separated.",
        updatedAt: at(30)
      }
    ],
    weather: [
      {
        id: "weather-003",
        headline: "Wind gusts peaking this hour",
        details: "High gusts may move smoke plumes rapidly across northbound sectors.",
        severity: "high",
        updatedAt: at(30)
      }
    ],
    sectionUpdatedAt: {
      alerts: at(30),
      evacuationPlans: at(30),
      connections: at(30),
      savedInformation: at(30),
      weather: at(30)
    },
    updateSummary: {
      alerts: 2,
      evacuationPlans: 1,
      connections: 3,
      savedInformation: 1,
      weather: 1
    }
  },
  {
    id: "step-5",
    simulatedAt: at(40),
    alerts: [
      {
        id: "inf-007",
        title: "Evacuation hold for completed zones",
        details: "Zones B and C reported over 90% clearance. Continue shelter-in-place if outside active zones.",
        urgency: "notification",
        category: "general",
        occurredAt: at(39),
        updatedAt: at(40),
        area: "County Wide",
        source: "Regional Emergency Management"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-003",
        title: "Post-Evacuation Check-In Guidance",
        successProbability: 88,
        summary: "Use check-in workflow to confirm safety and await return instructions.",
        steps: [
          "Complete shelter intake check-in.",
          "Confirm status with your emergency contact.",
          "Wait for official re-entry advisories."
        ],
        packingList: ["ID", "Medication", "Phone and charger"],
        updatedAt: at(40)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "416-555-0142",
        contactPhone: "416-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(40)
      },
      {
        id: "conn-002",
        ownerPhone: "416-555-0142",
        contactPhone: "647-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(40)
      },
      {
        id: "conn-003",
        ownerPhone: "416-555-0142",
        contactPhone: "437-555-0188",
        relationship: "dependent",
        trustLevel: 5,
        updatedAt: at(40)
      }
    ],
    savedInformation: [
      {
        id: "save-005",
        title: "Recovery Guidance",
        note: "Keep receipts, photo damage, and wait for municipal return notice.",
        updatedAt: at(40)
      }
    ],
    weather: [
      {
        id: "weather-004",
        headline: "Rainfall easing",
        details: "Precipitation rates are dropping; floodwater recession expected over coming hours.",
        severity: "moderate",
        updatedAt: at(40)
      }
    ],
    sectionUpdatedAt: {
      alerts: at(40),
      evacuationPlans: at(40),
      connections: at(40),
      savedInformation: at(40),
      weather: at(40)
    },
    updateSummary: {
      alerts: 1,
      evacuationPlans: 1,
      connections: 3,
      savedInformation: 1,
      weather: 1
    }
  }
];
