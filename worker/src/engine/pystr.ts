// Python's str() for the values the engine interpolates into text.
// Distances and other measurements are floats in the Python build, so 9 prints as "9.0".

export function pyStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return pyFloatStr(value);
  return String(value);
}

/** repr() of a Python float. */
export function pyFloatStr(x: number): string {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (Number.isInteger(x) && Math.abs(x) < 1e16) return `${x}.0`;
  return String(x);
}
