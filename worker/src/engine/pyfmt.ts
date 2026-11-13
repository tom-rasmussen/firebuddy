// Python formatting and rounding semantics, so the port's text matches the Python build exactly.

/** Python's round(x, nd): correctly rounded from the exact binary value, ties to even. */
export function pyRound(x: number, nd: number): number {
  if (!Number.isFinite(x)) return x;
  const fixed = x.toFixed(nd);
  const exact = Math.abs(x).toFixed(Math.min(100, nd + 60));
  const tail = exact.slice(exact.indexOf(".") + 1 + nd);
  const isTie = /^50*$/.test(tail);
  if (!isTie) return Number(fixed);
  // Exact tie: toFixed rounded away from zero; Python rounds to the even neighbour.
  const scale = 10 ** nd;
  const down = Math.trunc(Math.abs(x) * scale);
  const even = down % 2 === 0 ? down : down + 1;
  return (Math.sign(x) * even) / scale;
}

/** Python's f"{x:g}" (6 significant digits, trailing zeros stripped). */
export function fmtG(x: number): string {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0" : "0";
  const precision = 6;
  const [mantissa, expStr] = x.toExponential(precision - 1).split("e");
  const exp = Number(expStr);
  if (exp >= -4 && exp < precision) {
    const decimals = Math.max(0, precision - 1 - exp);
    return stripZeros(x.toFixed(decimals));
  }
  const sign = exp < 0 ? "-" : "+";
  const abs = Math.abs(exp);
  return `${stripZeros(mantissa ?? "")}e${sign}${abs < 10 ? "0" : ""}${abs}`;
}

function stripZeros(s: string): string {
  if (!s.includes(".")) return s;
  return s.replace(/0+$/, "").replace(/\.$/, "");
}

/** Python's f"{n:,}" for integers. */
export function fmtThousands(n: number): string {
  return Math.trunc(n).toLocaleString("en-US");
}
