declare module "expo-location" {
  export function requestForegroundPermissionsAsync(): Promise<{ status: string }>;
  export function getCurrentPositionAsync(options?: any): Promise<{
    coords: { latitude: number; longitude: number; altitude: number | null; accuracy: number | null };
  }>;
  export function watchPositionAsync(options: any, callback: (location: any) => void): Promise<{ remove(): void }>;
  export const Accuracy: Record<string, number>;
}
