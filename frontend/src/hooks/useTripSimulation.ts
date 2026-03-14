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
 * Project a point onto the nearest segment of a route.
 * Returns the elapsed time at the projected point, or null if the point
 * is more than `maxDistM` meters from any segment.
 */
function projectOntoRoute(
  point: Coordinate,
  coords: number[][],
  cumTime: number[],
  maxDistM = 200
): { elapsed: number; segIndex: number } | null {
  let bestDist = Infinity;
  let bestElapsed = 0;
  let bestSeg = 0;

  for (let i = 0; i < coords.length - 1; i++) {
    const ax = coords[i][0], ay = coords[i][1];
    const bx = coords[i + 1][0], by = coords[i + 1][1];
    const dx = bx - ax, dy = by - ay;
    const lenSq = dx * dx + dy * dy;

    // Parameter t along segment [0,1]
    let t = 0;
    if (lenSq > 0) {
      t = Math.max(0, Math.min(1, ((point.lng - ax) * dx + (point.lat - ay) * dy) / lenSq));
    }

    const projLng = ax + t * dx;
    const projLat = ay + t * dy;
    const dist = haversineDistance(point, { lng: projLng, lat: projLat });

    if (dist < bestDist) {
      bestDist = dist;
      bestSeg = i;
      const segDuration = cumTime[i + 1] - cumTime[i];
      bestElapsed = cumTime[i] + t * segDuration;
    }
  }

  if (Number.isFinite(maxDistM) && bestDist > maxDistM) return null;
  return { elapsed: bestElapsed, segIndex: bestSeg };
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
  const positionRef = useRef<Coordinate | null>(null);

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
      positionRef.current = null;
      setPosition(null);
      setBearing(0);
      setProgress(0);
      return;
    }

    const coords = geometry.coordinates;
    const fallbackTotal = 600; // 10 min fallback if no durations
    const { cumTime, totalTime } = buildCumulativeTime(segmentDurations, coords.length, fallbackTotal);

    if (totalTime === 0) return;

    // Smart reroute: if we have a current position (mid-trip), project onto the new route
    if (positionRef.current) {
      const proj = projectOntoRoute(positionRef.current, coords, cumTime, 1200);
      if (proj) {
        // Continue from the projected point on the new route
        elapsedRef.current = proj.elapsed;
        const segDuration = cumTime[proj.segIndex + 1] - cumTime[proj.segIndex];
        const t = segDuration > 0 ? (proj.elapsed - cumTime[proj.segIndex]) / segDuration : 0;
        setPosition(interpolatePosition(coords, proj.segIndex, t));
        setBearing(bearingAtSegment(coords, proj.segIndex));
        setProgress(proj.elapsed / totalTime);
      } else {
        // If route changed significantly, snap to nearest point instead of jumping back to route start.
        const nearest = projectOntoRoute(positionRef.current, coords, cumTime, Number.POSITIVE_INFINITY);
        if (nearest) {
          elapsedRef.current = nearest.elapsed;
          const segDuration = cumTime[nearest.segIndex + 1] - cumTime[nearest.segIndex];
          const t = segDuration > 0 ? (nearest.elapsed - cumTime[nearest.segIndex]) / segDuration : 0;
          setPosition(interpolatePosition(coords, nearest.segIndex, t));
          setBearing(bearingAtSegment(coords, nearest.segIndex));
          setProgress(nearest.elapsed / totalTime);
        }
      }
    } else {
      setPosition({ lng: coords[0][0], lat: coords[0][1] });
      setBearing(bearingAtSegment(coords, 0));
      setProgress(0);
      elapsedRef.current = 0;
    }

    let rafId: number;
    let lastFrameTime: number | null = null;

    const tick = (now: number) => {
      if (lastFrameTime === null) {
        lastFrameTime = now;
        rafId = requestAnimationFrame(tick);
        return;
      }

      if (!propPausedRef.current && !manualPausedRef.current) {
        const dtMs = Math.min(now - lastFrameTime, 100); // cap to avoid large jumps on tab-switch
        const newElapsed = elapsedRef.current + (dtMs / 1000) * timeScale;
        elapsedRef.current = Math.min(newElapsed, totalTime);

        const seg = findSegmentByTime(cumTime, elapsedRef.current);
        const segDuration = cumTime[seg + 1] - cumTime[seg];
        const t = segDuration > 0 ? (elapsedRef.current - cumTime[seg]) / segDuration : 0;

        const newPos = interpolatePosition(coords, seg, t);
        positionRef.current = newPos;
        setPosition(newPos);
        setBearing(bearingAtSegment(coords, seg));
        setProgress(elapsedRef.current / totalTime);

        if (elapsedRef.current >= totalTime) {
          lastFrameTime = now;
          return; // stop requesting frames
        }
      }

      lastFrameTime = now;
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(rafId);
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
