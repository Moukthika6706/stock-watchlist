// Groww brand mark: a circle split by a chart-like zig-zag line, blue above and
// mint green below. Drawn inline so it scales crisply at any size.
export default function GrowwLogo({ size = 52, className = '', title = 'Groww' }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={title}
      focusable="false"
    >
      <defs>
        <clipPath id="groww-mark-clip">
          <circle cx="50" cy="50" r="50" />
        </clipPath>
      </defs>
      <g clipPath="url(#groww-mark-clip)">
        <rect width="100" height="100" fill="#5367ff" />
        <path d="M-10 78 L36 47 L52 61 L110 32 L110 110 L-10 110 Z" fill="#00d09c" />
      </g>
    </svg>
  );
}
