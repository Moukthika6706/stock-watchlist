import { attentionFor, tintedPillStyle } from '../lib/attention';

export default function AttentionPill({ item }) {
  const category = item?.latest?.attention_category;
  const { label } = attentionFor(item);
  return (
    <span className="pill" style={tintedPillStyle(category)} title={category}>
      <span className="pill-dot" />
      {label}
    </span>
  );
}
