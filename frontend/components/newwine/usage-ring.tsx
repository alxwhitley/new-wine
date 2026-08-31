"use client";

const RADIUS = 15;
const STROKE_WIDTH = 4;
const CX = 20;
const CY = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS; // ≈ 94.25

interface UsageRingProps {
  used: number;
  limit: number;
  size?: number;
}

export function UsageRing({ used, limit, size = 40 }: UsageRingProps) {
  const fraction = limit > 0 ? Math.min(used / limit, 1) : 0;
  const filledArc = fraction * CIRCUMFERENCE;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 40 40"
        style={{ transform: "rotate(-90deg)" }}
        aria-label={`${used} of ${limit} weekly queries used`}
      >
        {/* Track: faint outline, always visible so ring never looks empty */}
        <circle
          cx={CX}
          cy={CY}
          r={RADIUS}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={STROKE_WIDTH}
        />
        {/* Arc: spent portion — grows as usage climbs */}
        {used > 0 && (
          <circle
            cx={CX}
            cy={CY}
            r={RADIUS}
            fill="none"
            stroke="hsl(var(--foreground))"
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            strokeDasharray={`${filledArc} ${CIRCUMFERENCE}`}
          />
        )}
      </svg>
      {/* Centered count label */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <span
          className="font-semibold text-foreground leading-none"
          style={{ fontSize: "0.5rem", letterSpacing: "-0.01em" }}
        >
          {used}/{limit}
        </span>
      </div>
    </div>
  );
}
