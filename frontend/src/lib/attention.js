// Single source of truth for attention categories. The backend returns exactly
// these four strings; every badge, pill and accent colour in the UI maps through
// this table so the digest and the table can never disagree.
//   Stable -> gray, Monitor -> yellow, Important -> orange, Immediate attention -> red
export const ATTENTION = {
  Stable: {
    key: 'stable',
    label: 'Stable',
    rank: 0,
    color: '#8a8f98',
    onColor: '#ffffff',
    tint: '#f1f3f5',
    onTint: '#4b5563',
  },
  Monitor: {
    key: 'monitor',
    label: 'Monitor',
    rank: 1,
    color: '#f5c400',
    onColor: '#2b2200',
    tint: '#fdf5d8',
    onTint: '#9a6b00',
  },
  Important: {
    key: 'important',
    label: 'Important',
    rank: 2,
    color: '#f2842a',
    onColor: '#2b1500',
    tint: '#fef0e1',
    onTint: '#c2410c',
  },
  'Immediate attention': {
    key: 'immediate',
    label: 'Immediate',
    rank: 3,
    color: '#e5383b',
    onColor: '#ffffff',
    tint: '#fde8e8',
    onTint: '#c8102e',
  },
};

export const STABLE = 'Stable';

export function attentionForCategory(category) {
  return ATTENTION[category] || ATTENTION[STABLE];
}

export function attentionFor(item) {
  return attentionForCategory(item?.latest?.attention_category);
}

// "Significant" = anything the backend did not classify as Stable. This is the
// one definition of N shared by the digest headline, summary line and row list.
export function isSignificant(item) {
  return Boolean(item?.latest) && item.latest.attention_category !== STABLE;
}

export function significantItems(items) {
  return items.filter(isSignificant).sort((a, b) => b.latest.attention_score - a.latest.attention_score);
}

// Inline-style helpers so the colours live here rather than in CSS classes.
export function solidBadgeStyle(category) {
  const a = attentionForCategory(category);
  return { background: a.color, color: a.onColor };
}

export function tintedPillStyle(category) {
  const a = attentionForCategory(category);
  return { background: a.tint, color: a.onTint };
}
