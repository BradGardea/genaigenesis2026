/**
 * Node-based generator for the community relationships dataset.
 * Mirrors the Python version for environments where Python isn't available.
 */

const fs = require("fs");
const path = require("path");

const FIRST_NAMES = [
  "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
  "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
  "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
  "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
  "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
  "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Melissa", "George", "Deborah",
  "Timothy", "Stephanie", "Jason", "Rebecca", "Jeffrey", "Sharon", "Ryan", "Laura",
  "Jacob", "Cynthia", "Gary", "Kathleen", "Nicholas", "Amy", "Eric", "Shirley",
];

const LAST_NAMES = [
  "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
  "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
  "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
  "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
  "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
  "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
  "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
  "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales",
];

const REL = ["dependent", "guardian", "friend", "acquaintance"];

const BASE_LON = 29.222;
const BASE_LAT = -1.679;
const PERSON_SCENARIOS = [
  "Severe storm evacuation support network",
  "Volcanic ash avoidance and mutual aid",
  "Flooded roads rideshare coordination",
  "Power outage welfare checks and pooling",
  "Wildfire smoke relocation carpool",
];

function parseArgs() {
  const defaults = { count: 60, minDegree: 3, maxDegree: 7, seed: 42, outfile: null };
  const args = { ...defaults };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    const next = argv[i + 1];
    const setInt = (field) => {
      if (next !== undefined) {
        args[field] = parseInt(next, 10);
        i++;
      }
    };
    if (key === "--count") setInt("count");
    else if (key === "--min-degree" || key === "--minDegree") setInt("minDegree");
    else if (key === "--max-degree" || key === "--maxDegree") setInt("maxDegree");
    else if (key === "--seed") setInt("seed");
    else if (key === "--outfile") {
      if (next !== undefined) {
        args.outfile = next;
        i++;
      }
    }
  }
  return args;
}

const args = parseArgs();

// Deterministic RNG (mulberry32)
function mulberry32(seed) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(args.seed);

function pick(list) {
  return list[Math.floor(rand() * list.length)];
}

function uniqueName(seen) {
  while (true) {
    const name = `${pick(FIRST_NAMES)} ${pick(LAST_NAMES)}`;
    if (!seen.has(name)) {
      seen.add(name);
      return name;
    }
  }
}

function randomPosition() {
  // North/south and west only: hard clamp to <= BASE_LON.
  const lon = BASE_LON - Math.abs(rand() * 0.025);
  const lat = BASE_LAT + (rand() * 0.05 - 0.025);
  return [Number(lon.toFixed(6)), Number(lat.toFixed(6))];
}

function buildPeople(count) {
  const names = new Set();
  const people = [];
  for (let i = 0; i < count; i++) {
    people.push({
      person_id: `p-${String(i + 1).padStart(3, "0")}`,
      name: uniqueName(names),
      seats_available: Math.max(0, Math.floor(rand() * 9 - rand() * 3)), // bias lower
      scenario: pick(PERSON_SCENARIOS),
      current_position: randomPosition(),
      connections: [],
    });
  }
  return people;
}

function connectPeople(people, minDegree, maxDegree) {
  const byId = Object.fromEntries(people.map((p) => [p.person_id, p]));
  for (const person of people) {
    const degree = Math.floor(rand() * (maxDegree - minDegree + 1)) + minDegree;
    const targets = people.filter((p) => p.person_id !== person.person_id);
    const picked = new Set();
    while (picked.size < degree && picked.size < targets.length) {
      picked.add(pick(targets));
    }
    for (const target of picked) {
      // Enforce rule: if you have a dependent, you do not have a guardian (and vice versa).
      const existing = new Set(person.connections.map((c) => c.relationship));
      let choices = [...REL];
      if (existing.has("dependent")) {
        choices = choices.filter((r) => r !== "guardian");
      }
      if (existing.has("guardian")) {
        choices = choices.filter((r) => r !== "dependent");
      }

      person.connections.push({
        target_person_id: target.person_id,
        relationship: pick(choices),
      });
      if (rand() < 0.55 && !byId[target.person_id].connections.some((c) => c.target_person_id === person.person_id)) {
        byId[target.person_id].connections.push({
          target_person_id: person.person_id,
          relationship: pick(REL),
        });
      }
    }
  }
}

function zeroSeatsForDependents(people) {
  const dependents = new Set();
  for (const person of people) {
    for (const connection of person.connections) {
      if (connection.relationship === "guardian") {
        dependents.add(connection.target_person_id);
      }
    }
  }
  for (const person of people) {
    if (dependents.has(person.person_id)) {
      person.seats_available = 0;
    }
  }
}

function buildPayload() {
  const people = buildPeople(args.count);
  connectPeople(people, args.minDegree, args.maxDegree);
  zeroSeatsForDependents(people);
  return {
    dataset_name: "goma_community_relationships_mock",
    version: "2.0",
    generated_at: new Date().toISOString(),
    scenario_note:
      "Algorithmically generated many-to-many social connections for evacuation and carpool planning near Goma, DR Congo, using American-style names.",
    scenario: "Severe storm evacuation support network",
    location: {
      name: "Goma, DR Congo",
      latitude: BASE_LAT,
      longitude: BASE_LON,
      timezone: "Africa/Lubumbashi",
    },
    schema_alignment: {
      person_schema_base: "PersonWithConnections / PersonConnectionsResponse",
      relationship_types: REL,
      position_format: "tuple [longitude, latitude] in decimal degrees",
    },
    persons: people,
  };
}

function main() {
  const payload = buildPayload();
  const outfile =
    args.outfile ||
    path.join(__dirname, "..", "..", "data", "goma_community_relationships_mock.json");
  fs.mkdirSync(path.dirname(outfile), { recursive: true });
  fs.writeFileSync(outfile, JSON.stringify(payload, null, 2));
  console.log(`Generated ${payload.persons.length} people to ${outfile}`);
}

main();
