import type { ReactNode } from "react";
export function OrbitMark() {
  return (
    <figure className="orbit-figure">
      <svg viewBox="0 0 380 320" aria-hidden="true" focusable="false">
        <defs>
          <clipPath id="orbit-boundary">
            <rect x="22" y="22" width="336" height="266" />
          </clipPath>
        </defs>
        <g fill="none" stroke="currentColor" strokeWidth=".8">
          <path d="M22 22h336v266H22z" opacity=".2" />
          <g clipPath="url(#orbit-boundary)">
            <ellipse
              cx="195"
              cy="164"
              rx="143"
              ry="112"
              transform="rotate(-23 195 164)"
            />
            <ellipse
              cx="177"
              cy="159"
              rx="102"
              ry="135"
              transform="rotate(38 177 159)"
            />
            <ellipse
              cx="185"
              cy="167"
              rx="58"
              ry="103"
              transform="rotate(-28 185 167)"
            />
            <path d="M-5 263 364 38M64 6l250 301M-15 148l417 47" opacity=".4" />
          </g>
          <path d="M12 22h20M22 12v20M348 288h20M358 278v20M178 161h14M185 154v14" />
        </g>
        <rect x="266" y="220" width="54" height="54" fill="var(--vermillion)" />
        <text
          x="293"
          y="251"
          textAnchor="middle"
          fill="var(--surface)"
          fontSize="17"
          fontFamily="Georgia,serif"
          letterSpacing="1"
        >
          GEO
        </text>
        <text x="23" y="308" fill="currentColor" fontSize="9" letterSpacing="3">
          OBSERVE / RECORD / REVISIT
        </text>
      </svg>
      <figcaption>观测路径示意 · 非数据图表</figcaption>
    </figure>
  );
}
export function Prelude({
  title,
  children,
  action,
  compact = false,
}: {
  title: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <section className={`prelude ${compact ? "compact" : ""}`}>
      <div className="prelude-copy">
        <p className="eyebrow">GEO / 运营档案</p>
        <h2>{title}</h2>
        <p className="prelude-description">{children}</p>
        {action}
        <p className="caption">原文留存　/　证据可追溯　/　不作因果承诺</p>
      </div>
      <OrbitMark />
    </section>
  );
}
