import type { KeyboardEvent, MouseEvent } from "react";
import type { BroadKind, NormalizedConceptAssignment } from "../lib/domain";
import type { RatingValue } from "../lib/types";
import { SvgIcon, iconForBroadKind } from "./icons";

export type RateHandler = (id: number, value: RatingValue) => void;
export type OpenHandler = (id: number) => void;

export function KindIcon({ broadKind, label }: { broadKind: BroadKind; label: string }) {
  return (
    <span className="kind-icon" title={label} aria-label={label}>
      <SvgIcon name={iconForBroadKind(broadKind)} title={label} />
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

/** Compact concept chip list; negative polarity is marked with a − prefix. */
export function ConceptChips({
  concepts,
  limit,
}: {
  concepts: NormalizedConceptAssignment[];
  limit: number;
}) {
  const shown = concepts.slice(0, limit);
  const overflow = concepts.length - shown.length;
  return (
    <div className="chips">
      {shown.map((concept) => (
        <span
          key={concept.conceptId}
          className={concept.polarity < 0 ? "chip negative" : "chip"}
          title={concept.description || concept.categoryLabel}
          aria-label={
            concept.polarity < 0 ? `${concept.label}, excluded` : `${concept.label}, weight ${concept.weight}`
          }
        >
          {concept.label} {concept.weight}
        </span>
      ))}
      {overflow > 0 ? <span className="chip more">+{overflow}</span> : null}
    </div>
  );
}

export function PaginationControls({
  page,
  pageCount,
  totalItems,
  pageSize,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageCount: number;
  totalItems: number;
  pageSize: number;
  pageSizeOptions: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Catalog pages">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        ‹ Prev
      </button>
      <span className="page-status" aria-live="polite">
        Page {page} of {pageCount} · {totalItems.toLocaleString()} results
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="Next page"
      >
        Next ›
      </button>
      <label className="page-size">
        Per page
        <select
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          aria-label="Results per page"
        >
          {pageSizeOptions.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
    </nav>
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
