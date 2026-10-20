// The Vyuh mark: three broken rings around a ball, after the Chakravyuh (the Mahabharata's spiral battle
// formation). Each ring opens in a different direction, like the layers of a formation.
export const RINGS = [
  { d: 'M40.21 9.45 A24 24 0 1 1 16.57 13.61', width: 3.0, opacity: 1 },
  { d: 'M42.61 44.64 A16.5 16.5 0 1 1 47.50 26.36', width: 2.8, opacity: 0.85 },
  { d: 'M22.64 33.65 A9.5 9.5 0 1 1 32.00 41.50', width: 2.6, opacity: 0.7 },
];

export default function LogoMark({ size = 28, ring = 'var(--mint)', ball = '#fff', className }: { size?: number; ring?: string; ball?: string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true">
      <g fill="none" stroke={ring} strokeLinecap="round">
        {RINGS.map((r) => <path key={r.d} d={r.d} strokeWidth={r.width} opacity={r.opacity} />)}
      </g>
      <circle cx="32" cy="32" r="4.2" fill={ball} />
    </svg>
  );
}
