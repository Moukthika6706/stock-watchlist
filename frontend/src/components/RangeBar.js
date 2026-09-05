import { compact } from '../lib/format';

// Where the current price sits inside the 52-week range.
export default function RangeBar({ low, high, price }) {
  let position = null;
  if (low != null && high != null && high > low && price != null) {
    position = Math.min(1, Math.max(0, (price - low) / (high - low)));
  }
  return (
    <div className="range" title={position == null ? undefined : `${Math.round(position * 100)}% of the way from the 52-week low to the high`}>
      <span className="range-label mono">{compact(low)}</span>
      <div className="range-track">
        {position != null && <span className="range-marker" style={{ left: `${position * 100}%` }} />}
      </div>
      <span className="range-label mono">{compact(high)}</span>
    </div>
  );
}
