// Port of firebuddy/geo.py.

export const EARTH_RADIUS_MI = 3958.8;

export const COMPASS_POINTS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
] as const;

const rad = (deg: number) => (deg * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Great-circle distance in statute miles. */
export function haversineMi(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = rad(lat1);
  const phi2 = rad(lat2);
  const dphi = rad(lat2 - lat1);
  const dlambda = rad(lon2 - lon1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlambda / 2) ** 2;
  const c = 2 * Math.asin(Math.min(1, Math.sqrt(a)));
  return EARTH_RADIUS_MI * c;
}

/** Initial compass bearing in degrees [0, 360) from point 1 to point 2. */
export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = rad(lat1);
  const phi2 = rad(lat2);
  const dlambda = rad(lon2 - lon1);
  const x = Math.sin(dlambda) * Math.cos(phi2);
  const y = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dlambda);
  return pyMod(deg(Math.atan2(x, y)) + 360, 360);
}

/** Nearest 16-point compass label. */
export function compass16(d: number): string {
  const idx = pyMod(pyRoundHalfEven(pyMod(d, 360) / 22.5), 16);
  return COMPASS_POINTS[idx] as string;
}

/** Smallest absolute angular difference, in [0, 180]. */
export function angularDiff(a: number, b: number): number {
  const diff = pyMod(Math.abs(a - b), 360);
  return diff > 180 ? 360 - diff : diff;
}

/** Python's % (result has the sign of the divisor). */
export function pyMod(a: number, n: number): number {
  return ((a % n) + n) % n;
}

/** Python's round(x) with no digits: ties to even. */
function pyRoundHalfEven(x: number): number {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}
