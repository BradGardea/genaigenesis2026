import { useCallback, useEffect, useRef, useState } from "react";
import { Coordinate, GeoJSONLineString } from "../types/domain";

interface TripSimulationResult {
  position: Coordinate | null;
  bearing: number;
  progress: number;
  /** Immediately freezes the simulation (no React re-render needed). */
  pause: () => void;
  /** Immediately resumes the simulation. */
  resume: () => void;
}

export function haversineDistance(a: Coordinate, b: Coordinate): number {
  const R = 6_371_000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const sinLat = Math.sin(dLat / 2);
  const sinLng = Math.sin(dLng / 2);
  const h = sinLat * sinLat + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * sinLng * sinLng;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function computeBearing(from: Coordinate, to: Coordinate): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const dLng = toRad(to.lng - from.lng);
  const lat1 = toRad(from.lat);
  const lat2 = toRad(to.lat);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

function buildCumulativeDistances(coords: number[][]): { cumDist: number[]; totalDist: number } {
  const cumDist = [0];
  for (let i = 1; i < coords.length; i++) {
    const a: Coordinate = { lng: coords[i - 1][0], lat: coords[i - 1][1] };
    const b: Coordinate = { lng: coords[i][0], lat: coords[i][1] };
    cumDist.push(cumDist[i - 1] + haversineDistance(a, b));
  }
  return { cumDist, totalDist: cumDist[cumDist.length - 1] };
}

function buildCumulativeTime(
  segmentDurations: number[] | undefined,
  coordCount: number,
  fallbackTotalSeconds: number
): { cumTime: number[]; totalTime: number } {
  const numSegments = coordCount - 1;
  const cumTime = [0];

  if (segmentDurations && segmentDurations.length >= numSegments) {
    for (let i = 0; i < numSegments; i++) {
      cumTime.push(cumTime[i] + segmentDurations[i]);
    }
  } else {
    const perSegment = fallbackTotalSeconds / numSegments;
    for (let i = 0; i < numSegments; i++) {
      cumTime.push(cumTime[i] + perSegment);
    }
  }

  return { cumTime, totalTime: cumTime[cumTime.length - 1] };
}

function findSegmentByTime(cumTime: number[], elapsed: number): number {
  let lo = 0;
  let hi = cumTime.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1;
    if (cumTime[mid] <= elapsed) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo;
}

function interpolatePosition(coords: number[][], segIndex: number, t: number): Coordinate {
  const a = coords[segIndex];
  const b = coords[Math.min(segIndex + 1, coords.length - 1)];
  return {
    lng: a[0] + t * (b[0] - a[0]),
    lat: a[1] + t * (b[1] - a[1]),
  };
}

function bearingAtSegment(coords: number[][], segIndex: number): number {
  const from: Coordinate = { lng: coords[segIndex][0], lat: coords[segIndex][1] };
  const toIdx = Math.min(segIndex + 1, coords.length - 1);
  const to: Coordinate = { lng: coords[toIdx][0], lat: coords[toIdx][1] };
  return computeBearing(from, to);
}

/**
 * Time-based simulation along a GeoJSON LineString using per-segment durations.
 * When segmentDurations is provided (from Mapbox annotations), the marker moves
 * at realistic road speeds — slow on residential streets, fast on highways.
 *
 * @param timeScale  Multiplier for wall-clock time. 10 = a 15-min drive plays in ~90s.
 */
export function useTripSimulation(
  geometry: GeoJSONLineString | null,
  segmentDurations: number[] | undefined,
  active: boolean,
  timeScale = 10,
  paused = false
): TripSimulationResult {
  const [position, setPosition] = useState<Coordinate | null>(null);
  const [bearing, setBearing] = useState(0);
  const [progress, setProgress] = useState(0);
  const elapsedRef = useRef(0);

  // Two independent pause signals — either one freezes the simulation.
  // propPaused tracks the React prop (e.g. rerouting state).
  // manualPaused is set imperatively via pause()/resume() with zero delay.
  const propPausedRef = useRef(paused);
  propPausedRef.current = paused;
  const manualPausedRef = useRef(false);

  const pause = useCallback(() => { manualPausedRef.current = true; }, []);
  const resume = useCallback(() => { manualPausedRef.current = false; }, []);

  useEffect(() => {
    manualPausedRef.current = false;

    if (!active || !geometry || geometry.coordinates.length < 2) {
      elapsedRef.current = 0;
      setPosition(null);
      setBearing(0);
      setProgress(0);
      return;
    }

    const coords = geometry.coordinates;
    const fallbackTotal = 600; // 10 min fallback if no durations
    const { cumTime, totalTime } = buildCumulativeTime(segmentDurations, coords.length, fallbackTotal);

    if (totalTime === 0) return;

    setPosition({ lng: coords[0][0], lat: coords[0][1] });
    setBearing(bearingAtSegment(coords, 0));
    setProgress(0);
    elapsedRef.current = 0;

    const tickMs = 500;

    const interval = setInterval(() => {
      if (propPausedRef.current || manualPausedRef.current) return;

      const newElapsed = elapsedRef.current + (tickMs / 1000) * timeScale;
      elapsedRef.current = Math.min(newElapsed, totalTime);

      const seg = findSegmentByTime(cumTime, elapsedRef.current);
      const segDuration = cumTime[seg + 1] - cumTime[seg];
      const t = segDuration > 0 ? (elapsedRef.current - cumTime[seg]) / segDuration : 0;

      setPosition(interpolatePosition(coords, seg, t));
      setBearing(bearingAtSegment(coords, seg));
      setProgress(elapsedRef.current / totalTime);

      if (elapsedRef.current >= totalTime) {
        clearInterval(interval);
      }
    }, tickMs);

    return () => clearInterval(interval);
  }, [active, geometry, segmentDurations, timeScale]);

  return { position, bearing, progress, pause, resume };
}

/**
 * Given a route geometry and a fraction (0-1), return the coordinate at that point.
 */
export function getPointAlongRoute(
  geometry: GeoJSONLineString,
  fraction: number
): Coordinate {
  const coords = geometry.coordinates;
  const { cumDist, totalDist } = buildCumulativeDistances(coords);
  const targetDist = Math.min(Math.max(fraction, 0), 1) * totalDist;

  for (let i = 1; i < coords.length; i++) {
    if (cumDist[i] >= targetDist) {
      const segStart = cumDist[i - 1];
      const segLen = cumDist[i] - segStart;
      const t = segLen > 0 ? (targetDist - segStart) / segLen : 0;
      return {
        lng: coords[i - 1][0] + t * (coords[i][0] - coords[i - 1][0]),
        lat: coords[i - 1][1] + t * (coords[i][1] - coords[i - 1][1]),
      };
    }
  }

  const last = coords[coords.length - 1];
  return { lng: last[0], lat: last[1] };
}
