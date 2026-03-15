import {
  CityStateStepResponse,
  ConnectionCreatePayload,
  EvacuationPlan,
  InfoBubble,
  PersonConnectionsResponse,
  SavedInformation,
  UserConnection,
  WeatherStepResponse,
  WeatherUpdate
} from "./types";

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function fetchInfoAlerts(): Promise<InfoBubble[]> {
  return fetchJson<InfoBubble[]>("/information/alerts");
}

export async function fetchEvacuationPlans(): Promise<EvacuationPlan[]> {
  return fetchJson<EvacuationPlan[]>("/information/evacuation-plans");
}

export async function fetchConnections(ownerPhone?: string): Promise<UserConnection[]> {
  const query = ownerPhone ? `?owner_phone=${encodeURIComponent(ownerPhone)}` : "";
  return fetchJson<UserConnection[]>(`/information/connections${query}`);
}

export async function createConnection(payload: ConnectionCreatePayload): Promise<void> {
  await fetchJson("/information/connections", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchSavedInformation(): Promise<SavedInformation[]> {
  return fetchJson<SavedInformation[]>("/information/saved");
}

export async function fetchWeatherUpdates(): Promise<WeatherUpdate[]> {
  return fetchJson<WeatherUpdate[]>("/information/weather");
}

export async function fetchWeatherCurrentStep(
  step: number,
  beautify = true
): Promise<WeatherStepResponse> {
  return fetchJson<WeatherStepResponse>(
    `/information/weather/current-step?step=${step}&beautify=${beautify}`
  );
}

export async function fetchWeatherNextStep(
  currStep: number,
  beautify = true
): Promise<WeatherStepResponse> {
  return fetchJson<WeatherStepResponse>(
    `/information/weather/next-step?curr_step=${currStep}&beautify=${beautify}`
  );
}

export async function fetchCityStateCurrentStep(
  step: number,
  beautify = true
): Promise<CityStateStepResponse> {
  return fetchJson<CityStateStepResponse>(
    `/information/city-state/current-step?step=${step}&beautify=${beautify}`
  );
}

export async function fetchCityStateNextStep(
  currStep: number,
  beautify = true
): Promise<CityStateStepResponse> {
  return fetchJson<CityStateStepResponse>(
    `/information/city-state/next-step?curr_step=${currStep}&beautify=${beautify}`
  );
}

export async function fetchFirstPersonConnections(): Promise<PersonConnectionsResponse> {
  return fetchJson<PersonConnectionsResponse>("/connections/first");
}
