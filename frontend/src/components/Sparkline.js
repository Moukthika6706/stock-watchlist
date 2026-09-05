// Tiny trend line drawn from the `sparkline` array GET /watchlist returns.
export default function Sparkline({ points, color = 'var(--up)', width = 130, height = 40 }) {
  let values = Array.isArray(points) ? points.filter((v) => typeof v === 'number') : [];
  if (values.length === 0) values = [0, 0];
  if (values.length === 1) values = [values[0], values[0]];

  const pad = 3;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (width - pad * 2) / (values.length - 1);

  const d = values
    .map((value, index) => {
      const x = pad + index * step;
      const y = height - pad - ((value - min) / span) * (height - pad * 2);
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
