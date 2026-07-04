import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { dateLabel, externalUrl, imageUrl, kindLabel } from "../lib/format";
import type { AppData, CatalogItem, Ratings } from "../lib/types";
import { KindIcon, RatingButtons, TagList, tagEntries } from "./common";
import type { RateHandler } from "./common";
import { SvgIcon } from "./icons";

export interface EntityWindow {
  id: number;
  x: number;
  y: number;
  z: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function clampWindowPosition(x: number, y: number, width: number, height: number) {
  const margin = 8;
  const maxX = Math.max(margin, window.innerWidth - width - margin);
  const maxY = Math.max(margin, window.innerHeight - height - margin);
  return { x: clamp(x, margin, maxX), y: clamp(y, margin, maxY) };
}

function isNarrowScreen(): boolean {
  return window.matchMedia("(max-width: 720px)").matches;
}

interface DragState {
  id: number;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
}

/** Shared floating-window state: every view opens entity windows through this. */
export function useEntityWindows() {
  const [windows, setWindows] = useState<EntityWindow[]>([]);
  const zIndex = useRef(30);
  const drag = useRef<DragState | null>(null);

  const nextZ = useCallback(() => {
    zIndex.current += 1;
    return zIndex.current;
  }, []);

  const openWindow = useCallback(
    (id: number) => {
      setWindows((current) => {
        const existing = current.find((win) => win.id === id);
        if (existing) {
          // Clicking the same entity focuses its window instead of duplicating it.
          return current.map((win) => (win.id === id ? { ...win, z: nextZ() } : win));
        }
        const width = 580;
        const height = 560;
        const pos = clampWindowPosition(56 + current.length * 28, 88 + current.length * 24, width, height);
        return [...current, { id, x: pos.x, y: pos.y, z: nextZ() }];
      });
    },
    [nextZ],
  );

  const focusWindow = useCallback(
    (id: number) => {
      setWindows((current) => current.map((win) => (win.id === id ? { ...win, z: nextZ() } : win)));
    },
    [nextZ],
  );

  const closeWindow = useCallback((id: number) => {
    if (drag.current?.id === id) drag.current = null;
    setWindows((current) => current.filter((win) => win.id !== id));
  }, []);

  const startDrag = useCallback(
    (event: ReactPointerEvent<HTMLElement>, win: EntityWindow) => {
      if (isNarrowScreen()) return;
      if (event.button !== 0) return;
      // Never start a drag from a button; it would swallow the click.
      if ((event.target as HTMLElement).closest("button")) return;
      const panel = (event.currentTarget as HTMLElement).closest(".entity-window");
      if (!panel) return;
      const rect = panel.getBoundingClientRect();
      drag.current = {
        id: win.id,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
        width: rect.width,
        height: rect.height,
      };
      focusWindow(win.id);
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    },
    [focusWindow],
  );

  useEffect(() => {
    function onMove(event: PointerEvent) {
      const active = drag.current;
      if (!active) return;
      event.preventDefault();
      const next = clampWindowPosition(
        event.clientX - active.offsetX,
        event.clientY - active.offsetY,
        active.width,
        active.height,
      );
      setWindows((current) =>
        current.map((win) => (win.id === active.id ? { ...win, x: next.x, y: next.y } : win)),
      );
    }
    function onEnd() {
      drag.current = null;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onEnd);
    window.addEventListener("pointercancel", onEnd);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
      window.removeEventListener("pointercancel", onEnd);
    };
  }, []);

  // Escape closes the top-most window.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setWindows((current) => {
        if (!current.length) return current;
        const top = current.reduce((a, b) => (b.z > a.z ? b : a));
        return current.filter((win) => win.id !== top.id);
      });
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Keep windows inside the viewport when it shrinks.
  useEffect(() => {
    function onResize() {
      setWindows((current) =>
        current.map((win) => {
          const pos = clampWindowPosition(win.x, win.y, 580, 560);
          return pos.x === win.x && pos.y === win.y ? win : { ...win, ...pos };
        }),
      );
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { windows, openWindow, focusWindow, closeWindow, startDrag };
}

export function FloatingEntityWindows({
  windows,
  data,
  ratings,
  onFocus,
  onClose,
  onDragStart,
  onRate,
}: {
  windows: EntityWindow[];
  data: AppData;
  ratings: Ratings;
  onFocus: (id: number) => void;
  onClose: (id: number) => void;
  onDragStart: (event: ReactPointerEvent<HTMLElement>, win: EntityWindow) => void;
  onRate: RateHandler;
}) {
  return (
    <>
      {windows.map((win) => {
        const item = data.catalogById.get(win.id);
        if (!item) return null;
        return (
          <article
            key={win.id}
            className="entity-window"
            style={{ left: `${win.x}px`, top: `${win.y}px`, zIndex: win.z }}
            onPointerDown={() => onFocus(win.id)}
            aria-label={`Details for ${item.label}`}
          >
            <header className="window-header" onPointerDown={(event) => onDragStart(event, win)}>
              <div className="window-title">
                <strong>{item.label}</strong>
                <span>
                  {[dateLabel(item.date, item.datePrecision), kindLabel(item.kind)].filter(Boolean).join(" / ")}
                </span>
              </div>
              <button
                type="button"
                className="icon-button close-button"
                onClick={(event) => {
                  event.stopPropagation();
                  onClose(win.id);
                }}
                title="Close"
                aria-label={`Close ${item.label}`}
              >
                <SvgIcon name="close" title="Close" />
              </button>
            </header>
            <EntityDetails item={item} data={data} rating={ratings[String(item.id)] || 0} onRate={onRate} />
          </article>
        );
      })}
    </>
  );
}

function EntityDetails({
  item,
  data,
  rating,
  onRate,
}: {
  item: CatalogItem;
  data: AppData;
  rating: number;
  onRate: RateHandler;
}) {
  const image = imageUrl(item.image);
  const refs = item.refs || [];
  return (
    <div className="entity-body">
      {image ? (
        <img className="entity-image" src={image} alt={item.label} loading="lazy" />
      ) : (
        <div className="entity-image placeholder" />
      )}
      <div className="entity-main">
        <div className="entity-meta">
          <KindIcon kind={item.kind} />
          <span>{dateLabel(item.date, item.datePrecision) || "undated"}</span>
        </div>
        <RatingButtons id={item.id} label={item.label} rating={rating} onRate={onRate} />
        <TagList entries={tagEntries(item, data)} initialLimit={12} expandable />
        {refs.length ? (
          <div className="ref-list">
            {refs.map((ref) => {
              const url = externalUrl(ref);
              return url ? (
                <a key={`${ref[0]}-${ref[1]}`} href={url} target="_blank" rel="noreferrer">
                  {ref[0]}
                </a>
              ) : (
                <span key={`${ref[0]}-${ref[1]}`}>{ref[0]}</span>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
}
