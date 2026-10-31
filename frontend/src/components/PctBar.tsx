// Draws a percentage the backend computed (0-100). Nothing is calculated here.

export default function PctBar({ value, label }: { value: number; label: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <span className="pct">
      <svg className="bar pct-bar" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label={`${label} ${value}%`}>
        <rect className="track" x={0} y={0} width={100} height={8} />
        {width > 0 && <rect className="pct-fill" x={0} y={0} width={width} height={8} />}
      </svg>
      <span className="pct-num" aria-hidden="true">
        {value}%
      </span>
    </span>
  );
}
