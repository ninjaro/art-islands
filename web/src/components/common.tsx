import { useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { kindLabel } from "../lib/format";
import type { AppData, CatalogItem, RatingValue, Tag } from "../lib/types";
import { SvgIcon, kindIconName } from "./icons";

export type RateHandler = (id: number, value: RatingValue) => void;
export type OpenHandler = (id: number) => void;

export function KindIcon({ kind }: { kind: number }) {
  const label = kindLabel(kind);
  return (
    <span className="kind-icon" title={label} aria-label={label}>
      <SvgIcon name={kindIconName(kind)} title={label} />
    </span>
  );
}

export function RatingButtons({
  id,
  label,
  rating,
  onRate,
}: {
  id: number;
  label: string;
  rating: number;
  onRate: RateHandler;
}) {
  return (
    <div className="rating-buttons" onClick={(event: MouseEvent) => event.stopPropagation()}>
      <button
        type="button"
        className={rating === 1 ? "icon-button rating active like" : "icon-button rating like"}
        onClick={() => onRate(id, 1)}
        title={`Like ${label}`}
        aria-label={`Like ${label}`}
        aria-pressed={rating === 1}
      >
        <SvgIcon name="like" title={`Like ${label}`} />
      </button>
      <button
        type="button"
        className={rating === -1 ? "icon-button rating active dislike" : "icon-button rating dislike"}
        onClick={() => onRate(id, -1)}
        title={`Dislike ${label}`}
        aria-label={`Dislike ${label}`}
        aria-pressed={rating === -1}
      >
        <SvgIcon name="dislike" title={`Dislike ${label}`} />
      </button>
    </div>
  );
}

export interface TagChipEntry {
  tag: Tag;
  weight: number;
  polarity: number;
}

export function tagEntries(item: CatalogItem, data: AppData): TagChipEntry[] {
  return (item.tags || [])
    .map(([tagId, weight, polarity]) => ({ tag: data.tagById.get(tagId), weight, polarity }))
    .filter((entry): entry is TagChipEntry => Boolean(entry.tag))
    .sort((a, b) => b.weight - a.weight || a.tag.name.localeCompare(b.tag.name));
}

export function TagList({
  entries,
  initialLimit,
  expandable,
}: {
  entries: TagChipEntry[];
  initialLimit: number;
  expandable: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const limited = expanded ? entries : entries.slice(0, initialLimit);
  const overflow = entries.length > initialLimit;

  return (
    <div className={expanded ? "tag-block expanded" : "tag-block"}>
      <div className="chips">
        {limited.map(({ tag, weight, polarity }) => (
          <span
            key={tag.id}
            className={`chip ${polarity > 0 ? "positive" : polarity < 0 ? "negative" : ""}`}
            title={tag.description || ""}
          >
            {tag.name} {weight}
          </span>
        ))}
        {!expandable && overflow ? <span className="chip more">+{entries.length - initialLimit}</span> : null}
      </div>
      {expandable && overflow ? (
        <button type="button" className="tag-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Collapse" : `Show all (${entries.length})`}
        </button>
      ) : null}
    </div>
  );
}

/** Keyboard-accessible clickable table row props (audit fix carried over). */
export function rowInteractionProps(id: number, label: string, onOpen: OpenHandler) {
  return {
    tabIndex: 0,
    role: "button",
    "aria-label": `Open details for ${label}`,
    onClick: () => onOpen(id),
    onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if ((event.target as HTMLElement).closest("button, input, select, a")) return;
      event.preventDefault();
      onOpen(id);
    },
  };
}
