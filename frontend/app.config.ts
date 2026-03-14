import "dotenv/config";
import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "CrisisNet",
  slug: "crisisnet",
  scheme: "crisisnet",
  version: "0.1.0",
  orientation: "portrait",
  userInterfaceStyle: "automatic",
  assetBundlePatterns: ["**/*"],
  web: {
    bundler: "metro"
  },
  extra: {
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1",
    mapboxPublicToken: process.env.EXPO_PUBLIC_MAPBOX_ACCESS_TOKEN ?? ""
  }
};

export default config;
