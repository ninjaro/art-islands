import type { ReactNode } from "react";
import type { BroadKind } from "../lib/domain";

const lineProps = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  strokeWidth: 2,
} as const;

function iconNodes(name: string): ReactNode {
  if (name === "close") {
    return (
      <>
        <path {...lineProps} d="M18 6 6 18" />
        <path {...lineProps} d="m6 6 12 12" />
      </>
    );
  }
  if (name === "like") {
    return (
      <>
        <path {...lineProps} d="M7 10v11" />
        <path {...lineProps} d="M15 5.5 14 10h5.5a2 2 0 0 1 2 2.4l-1.2 6a3 3 0 0 1-3 2.6H7l-4-1V10h4l5-7a2 2 0 0 1 3 2.5Z" />
      </>
    );
  }
  if (name === "dislike") {
    return (
      <>
        <path {...lineProps} d="M7 14V3" />
        <path {...lineProps} d="M15 18.5 14 14h5.5a2 2 0 0 0 2-2.4l-1.2-6a3 3 0 0 0-3-2.6H7L3 4v10h4l5 7a2 2 0 0 0 3-2.5Z" />
      </>
    );
  }
  if (name === "film") {
    return (
      <>
        <rect {...lineProps} x={3} y={4} width={18} height={16} rx={2} />
        <path {...lineProps} d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" />
      </>
    );
  }
  if (name === "music") {
    return (
      <>
        <path {...lineProps} d="M9 18V5l10-2v13" />
        <circle {...lineProps} cx={6} cy={18} r={3} />
        <circle {...lineProps} cx={16} cy={16} r={3} />
      </>
    );
  }
  if (name === "game") {
    return (
      <>
        <path {...lineProps} d="M6 12h4m-2-2v4" />
        <path {...lineProps} d="M15 13h.01M18 11h.01" />
        <path {...lineProps} d="M5 8h14a3 3 0 0 1 3 3v4a4 4 0 0 1-7 2.5L13.5 16h-3L9 17.5A4 4 0 0 1 2 15v-4a3 3 0 0 1 3-3Z" />
      </>
    );
  }
  if (name === "book") {
    return (
      <>
        <path {...lineProps} d="M3 5.5A2.5 2.5 0 0 1 5.5 3H21v16H6a3 3 0 0 0-3 3Z" />
        <path {...lineProps} d="M3 5.5v14A2.5 2.5 0 0 1 5.5 17H21" />
      </>
    );
  }
  return (
    <>
      <circle {...lineProps} cx={12} cy={12} r={9} />
      <path {...lineProps} d="M9.5 9a2.5 2.5 0 0 1 4.7 1.2c0 1.8-2.2 2-2.2 3.8" />
      <path {...lineProps} d="M12 17h.01" />
    </>
  );
}

export function SvgIcon({ name, title, size = 18 }: { name: string; title: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} role="img" aria-label={title} focusable="false">
      <title>{title}</title>
      {iconNodes(name)}
    </svg>
  );
}

export function iconForBroadKind(kind: BroadKind): string {
  if (kind === "film" || kind === "tv") return "film";
  if (kind === "music") return "music";
  if (kind === "game") return "game";
  return "book";
}
