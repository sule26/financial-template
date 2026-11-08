/**
 * Guilloché — the fine-line security pattern printed on banknotes. Used once, on the month banknote
 * (signature element of the "Cédula" visual system) and, tiny, in the wordmark.
 *
 * Generated geometry (hypotrochoid rosette + sine bands), drawn as inline SVG: no external asset,
 * nothing for the CSP to block.
 */
import { useMemo } from "react";

/** Points of a hypotrochoid (spirograph) curve as an SVG path. */
export function rosettePath(
  R: number,
  r: number,
  d: number,
  cx: number,
  cy: number,
  steps = 720,
): string {
  const parts: string[] = [];
  // Closed after lcm-ish turns: r/gcd(R, r) revolutions of the rolling circle.
  const turns = r / gcd(Math.round(R), Math.round(r));
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2 * turns;
    const k = (R - r) / r;
    const x = cx + (R - r) * Math.cos(t) + d * Math.cos(k * t);
    const y = cy + (R - r) * Math.sin(t) - d * Math.sin(k * t);
    parts.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  return parts.join("") + "Z";
}

function gcd(a: number, b: number): number {
  return b === 0 ? Math.abs(a) || 1 : gcd(b, a % b);
}

/** Horizontal sine bands like the background print of a note. */
export function wavePath(
  width: number,
  y: number,
  amp: number,
  period: number,
  phase: number,
) {
  const parts: string[] = [];
  for (let x = 0; x <= width; x += 4) {
    const yy = y + amp * Math.sin((x / period) * Math.PI * 2 + phase);
    parts.push(`${x === 0 ? "M" : "L"}${x} ${yy.toFixed(2)}`);
  }
  return parts.join("");
}

export function Guilloche({ className }: { className?: string }) {
  const rosettes = useMemo(
    () => [
      rosettePath(150, 40, 70, 160, 160),
      rosettePath(120, 36, 52, 160, 160),
      rosettePath(90, 30, 40, 160, 160),
    ],
    [],
  );
  const waves = useMemo(
    () =>
      Array.from({ length: 9 }, (_, i) =>
        wavePath(640, 30 + i * 30, 7, 120, i * 0.6),
      ),
    [],
  );
  return (
    <svg
      className={className}
      viewBox="0 0 640 320"
      preserveAspectRatio="xMaxYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g
        className="et-guilloche__waves"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.5"
      >
        {waves.map((d, i) => (
          <path key={i} d={d} />
        ))}
      </g>
      <g
        className="et-guilloche__rosette"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.7"
        transform="translate(360 0)"
      >
        {rosettes.map((d, i) => (
          <path key={i} d={d} opacity={1 - i * 0.22} />
        ))}
      </g>
    </svg>
  );
}

/** Small mark for the wordmark: a rosette inside a jade coin. */
export function BrandMark({ size = 30 }: { size?: number }) {
  const d = useMemo(() => rosettePath(13, 4, 6, 16, 16, 240), []);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      {/* R14.18: CSS (not SVG attributes) so the accent variables always resolve */}
      <circle
        cx="16"
        cy="16"
        r="15.5"
        style={{ fill: "var(--et-note-from)" }}
      />
      <path
        d={d}
        fill="none"
        style={{ stroke: "var(--et-note-brass)" }}
        strokeWidth="0.9"
      />
    </svg>
  );
}
