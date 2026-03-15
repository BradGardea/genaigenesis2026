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
        title: "Heavy rainfall detected near Vilankulo coastline",
        details: "Sustained rainfall exceeding 40mm/hr observed moving inland. Low-lying areas along the EN1 corridor should prepare for surface water accumulation. Secure loose items and move to higher ground if in a flood-prone zone.",
        urgency: "warning",
        category: "hazard update",
        occurredAt: at(-5),
        updatedAt: at(0),
        area: "Vilankulo Coast",
        status: "Developing",
        lat: -23.92,
        lon: 35.32
      },
      {
        id: "inf-002",
        title: "Wind speeds increasing across exposed areas",
        details: "Gusts of 65 km/h recorded along the beachfront and airport road. Unsecured roofing and signage may become hazardous. Avoid unnecessary travel in open areas.",
        urgency: "caution",
        category: "hazard update",
        occurredAt: at(-3),
        updatedAt: at(0),
        area: "Vilankulo Beachfront",
        status: "Intensifying",
        lat: -22.00,
        lon: 35.33
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Primary Route: Inland via EN1 Southbound",
        successProbability: 72,
        summary: "Depart before road conditions deteriorate. Regroup at Vilankulo Secondary School.",
        steps: [
          "Pack essentials for 24 hours.",
          "Head south on EN1 toward Inhambane.",
          "Check in at Vilankulo Secondary School assembly point."
        ],
        packingList: ["ID and medication", "Phone charger", "Water and food", "Rain cover"],
        updatedAt: at(0)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-84-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(0)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Emergency Assembly Point",
        note: "Vilankulo Secondary School, Bairro 5. Report to the main hall.",
        updatedAt: at(0)
      }
    ],
    weather: [
      {
        id: "weather-001",
        headline: "Tropical cyclone approaching from the east",
        details: "A severe tropical system is tracking westward toward the Mozambique Channel coast. Landfall expected within 6 hours near Vilankulo.",
        severity: "high",
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
        id: "inf-003",
        title: "Flash flooding confirmed along EN1 drainage channels",
        details: "Water levels rising rapidly in low sections of the EN1 between Vilankulo and the airport. Several vehicles reported stranded. Do not attempt to cross flooded road sections on foot or by vehicle.",
        urgency: "urgent alert",
        category: "hazard update",
        occurredAt: at(6),
        updatedAt: at(10),
        area: "EN1 South of Vilankulo",
        status: "Worsening",
        lat: -22.01,
        lon: 35.31
      },
      {
        id: "inf-004",
        title: "Road closure reported near Vilankulo market area",
        details: "Debris and standing water have forced closure of the central market access road. Municipal crews are unable to clear until wind subsides. Use alternate routes via Bairro 7.",
        urgency: "alert",
        category: "closure",
        occurredAt: at(8),
        updatedAt: at(10),
        area: "Vilankulo Central Market",
        status: "Active",
        lat: -22.00,
        lon: 35.32
      },
      {
        id: "inf-005",
        title: "Keep emergency radio frequencies monitored",
        details: "Cell tower coverage is intermittent due to wind damage. Tune to Radio Mozambique 97.9 FM for real-time updates. Conserve phone battery for essential communication only.",
        urgency: "notification",
        category: "advisory",
        occurredAt: at(9),
        updatedAt: at(10),
        area: "Vilankulo Region",
        status: "Ongoing"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Primary Route: Inland via EN1 Southbound",
        successProbability: 58,
        summary: "EN1 sections are flooding. Move now if accessible or shelter in place at a reinforced structure.",
        steps: [
          "Notify your emergency contact.",
          "If EN1 is passable, proceed south immediately.",
          "If blocked, move to the nearest concrete building above ground level."
        ],
        packingList: ["Medication", "Water", "Phone and charger", "Documents in waterproof bag"],
        updatedAt: at(10)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-84-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(10)
      },
      {
        id: "conn-002",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-87-555-0126",
        relationship: "friend",
        trustLevel: 3,
        updatedAt: at(10)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Emergency Assembly Point",
        note: "Vilankulo Secondary School, Bairro 5. Report to the main hall.",
        updatedAt: at(0)
      },
      {
        id: "save-002",
        title: "Alternate Shelter",
        note: "Hospital Provincial de Vilankulo, ground floor intake.",
        updatedAt: at(10)
      }
    ],
    weather: [
      {
        id: "weather-001",
        headline: "Cyclone making landfall",
        details: "Eye wall approaching the coast. Maximum sustained winds of 120 km/h with gusts exceeding 160 km/h. Expect the most dangerous conditions in the next 2 hours.",
        severity: "extreme",
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
        id: "inf-006",
        title: "Structural damage observed in Bairro 3",
        details: "Multiple roof collapses reported in residential areas. Concrete block walls showing fractures near the waterfront. Residents in damaged structures should relocate immediately to the school or hospital shelters.",
        urgency: "extreme urgency alert",
        category: "hazard update",
        occurredAt: at(18),
        updatedAt: at(20),
        area: "Bairro 3, Vilankulo",
        status: "Critical",
        lat: -22.00,
        lon: 35.34
      },
      {
        id: "inf-007",
        title: "Debris blocking multiple roads in central Vilankulo",
        details: "Fallen trees and corrugated roofing are obstructing vehicle passage on at least three central roads. Foot travel is hazardous due to flying debris. Remain sheltered until wind speeds drop below 60 km/h.",
        urgency: "urgent alert",
        category: "hazard update",
        occurredAt: at(19),
        updatedAt: at(20),
        area: "Vilankulo Town Center",
        status: "Worsening",
        lat: -22.00,
        lon: 35.32
      },
      {
        id: "inf-008",
        title: "Ensure all household members are accounted for",
        details: "If you are separated from family, remain in your current shelter and use SMS to communicate your location. Do not travel during peak storm conditions. Emergency responders will coordinate reunification after the storm passes.",
        urgency: "caution",
        category: "advisory",
        occurredAt: at(20),
        updatedAt: at(20),
        area: "Vilankulo Region",
        status: "Guidance"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Shelter in Place",
        successProbability: 82,
        summary: "Road conditions no longer allow safe evacuation. Move to the strongest interior room.",
        steps: [
          "Stay away from windows and exterior walls.",
          "Move to an interior room on the lowest level.",
          "Keep your emergency supplies within reach."
        ],
        packingList: ["Water", "Medication", "Flashlight", "Radio"],
        updatedAt: at(20)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-84-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(20)
      },
      {
        id: "conn-002",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-87-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(20)
      }
    ],
    savedInformation: [
      {
        id: "save-001",
        title: "Emergency Assembly Point",
        note: "Vilankulo Secondary School, Bairro 5. Report to the main hall.",
        updatedAt: at(0)
      },
      {
        id: "save-003",
        title: "Emergency Radio",
        note: "Radio Mozambique 97.9 FM for official updates.",
        updatedAt: at(20)
      }
    ],
    weather: [
      {
        id: "weather-002",
        headline: "Eye wall passing over Vilankulo",
        details: "Maximum intensity conditions. Winds exceeding 150 km/h with torrential rain. Brief calm expected if the eye passes directly overhead \u2014 do not leave shelter during the calm.",
        severity: "extreme",
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
      alerts: 3,
      evacuationPlans: 1,
      connections: 2,
      savedInformation: 1,
      weather: 1
    }
  },
  {
    id: "step-4",
    simulatedAt: at(30),
    alerts: [
      {
        id: "inf-009",
        title: "Widespread flooding across southern Vilankulo",
        details: "Floodwater depth exceeding 1 metre in Bairro 4 and along the airport access road. Several structures partially submerged. Water is contaminated \u2014 do not wade through floodwater without protective footwear.",
        urgency: "extreme urgency alert",
        category: "hazard update",
        occurredAt: at(28),
        updatedAt: at(30),
        area: "Bairro 4, Vilankulo",
        status: "Critical",
        lat: -22.01,
        lon: 35.29
      },
      {
        id: "inf-010",
        title: "Road closure on airport access route",
        details: "The main road to Vilankulo Airport is impassable due to 80 cm of standing water and debris accumulation. No estimated reopening time. Airport operations are suspended.",
        urgency: "alert",
        category: "closure",
        occurredAt: at(29),
        updatedAt: at(30),
        area: "VNX Airport Road",
        status: "Active",
        lat: -22.01,
        lon: 35.31
      },
      {
        id: "inf-011",
        title: "Boil all drinking water until further notice",
        details: "Municipal water supply may be contaminated due to flooding at treatment facilities. Boil water for at least 3 minutes before drinking. Use purification tablets if boiling is not possible.",
        urgency: "warning",
        category: "advisory",
        occurredAt: at(30),
        updatedAt: at(30),
        area: "Vilankulo Municipality",
        status: "Guidance"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-001",
        title: "Shelter in Place \u2014 Storm weakening",
        successProbability: 76,
        summary: "Wind speeds are beginning to decrease. Continue sheltering until an all-clear is issued.",
        steps: [
          "Remain in your current shelter.",
          "Monitor Radio Mozambique 97.9 FM.",
          "Prepare to assist neighbours once conditions allow."
        ],
        packingList: ["Water", "First aid kit", "Torch", "Dry clothing"],
        updatedAt: at(30)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-84-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(30)
      },
      {
        id: "conn-002",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-87-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(30)
      },
      {
        id: "conn-003",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-82-555-0188",
        relationship: "dependent",
        trustLevel: 5,
        updatedAt: at(30)
      }
    ],
    savedInformation: [
      {
        id: "save-004",
        title: "Water Safety",
        note: "Boil all water for 3 minutes. Use purification tablets if no heat source available.",
        updatedAt: at(30)
      }
    ],
    weather: [
      {
        id: "weather-003",
        headline: "Storm centre moving inland",
        details: "Wind speeds gradually reducing to 90 km/h. Heavy rain continues. Flooding will persist for several hours even after rain stops due to runoff from saturated ground.",
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
      alerts: 3,
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
        id: "inf-012",
        title: "Wind speeds dropping below dangerous thresholds",
        details: "Sustained winds now below 70 km/h and continuing to decrease. It is becoming safer to assess immediate surroundings but remain cautious of weakened structures and downed power lines.",
        urgency: "warning",
        category: "hazard update",
        occurredAt: at(38),
        updatedAt: at(40),
        area: "Vilankulo Region",
        status: "Easing",
        lat: -21.99,
        lon: 35.33
      },
      {
        id: "inf-013",
        title: "Flooding persists in low-lying areas",
        details: "Water recession is slow in Bairro 4 and along the EN1 corridor. Do not return to flooded properties until water has fully receded and structures have been inspected.",
        urgency: "caution",
        category: "hazard update",
        occurredAt: at(39),
        updatedAt: at(40),
        area: "Bairro 4, EN1 Corridor",
        status: "Persisting",
        lat: -22.01,
        lon: 35.30
      },
      {
        id: "inf-014",
        title: "Document damage before cleanup begins",
        details: "Photograph all property damage before moving debris. Keep receipts for emergency expenses. Contact municipal disaster relief offices when they reopen for assistance registration.",
        urgency: "notification",
        category: "advisory",
        occurredAt: at(40),
        updatedAt: at(40),
        area: "Vilankulo Municipality",
        status: "Guidance"
      }
    ],
    evacuationPlans: [
      {
        id: "plan-003",
        title: "Post-Storm Safety Assessment",
        successProbability: 88,
        summary: "Storm is weakening. Follow guidance before leaving shelter.",
        steps: [
          "Wait for official all-clear on Radio Mozambique.",
          "Check for structural damage before re-entering buildings.",
          "Report injuries or trapped persons to emergency services."
        ],
        packingList: ["Sturdy shoes", "First aid kit", "Torch", "Phone"],
        updatedAt: at(40)
      }
    ],
    connections: [
      {
        id: "conn-001",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-84-555-0179",
        relationship: "guardian",
        trustLevel: 5,
        updatedAt: at(40)
      },
      {
        id: "conn-002",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-87-555-0126",
        relationship: "friend",
        trustLevel: 4,
        updatedAt: at(40)
      },
      {
        id: "conn-003",
        ownerPhone: "+258-84-555-0142",
        contactPhone: "+258-82-555-0188",
        relationship: "dependent",
        trustLevel: 5,
        updatedAt: at(40)
      }
    ],
    savedInformation: [
      {
        id: "save-005",
        title: "Recovery Guidance",
        note: "Photograph all damage. Keep receipts. Wait for municipal return-to-home notice.",
        updatedAt: at(40)
      }
    ],
    weather: [
      {
        id: "weather-004",
        headline: "Storm weakening, rain tapering",
        details: "Cyclone is moving further inland and losing intensity. Rainfall rates are dropping. Floodwater recession will take several hours. Remain vigilant for secondary hazards.",
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
      alerts: 3,
      evacuationPlans: 1,
      connections: 3,
      savedInformation: 1,
      weather: 1
    }
  }
];
