import { useMemo } from "react";
import { dateLabel, kindLabel } from "../lib/format";
import type { AppData, CatalogItem, Ratings, Tag } from "../lib/types";
import { KindIcon, RatingButtons, TagList, rowInteractionProps, tagEntries } from "../components/common";
import type { OpenHandler, RateHandler } from "../components/common";

export interface Filters {
  q: string;
  minDate: string;
  maxDate: string;
  kind: string;
  tag: string;
}

export const EMPTY_FILTERS: Filters = { q: "", minDate: "", maxDate: "", kind: "", tag: "" };

export function filterCatalog(data: AppData, filters: Filters): CatalogItem[] {
  const q = filters.q.trim().toLowerCase();
  return data.catalog.filter((item) => {
    if (filters.kind && String(item.kind) !== filters.kind) return false;
    if (filters.minDate && (!item.date || item.date < filters.minDate)) return false;
    if (filters.maxDate && (!item.date || item.date > filters.maxDate)) return false;
    if (filters.tag && !item.tags.some(([tagId]) => String(tagId) === filters.tag)) return false;
    if (!q) return true;

    const tagHit = item.tags.some(([tagId]) => {
      const tag = data.tagById.get(tagId);
      return tag ? tag.name.toLowerCase().includes(q) : false;
    });
    return item.label.toLowerCase().includes(q) || tagHit;
  });
}

export function sortCatalog(items: CatalogItem[], sortMode: string): CatalogItem[] {
  const copy = [...items];
  if (sortMode === "label") {
    return copy.sort((a, b) => a.label.localeCompare(b.label) || a.id - b.id);
  }
  if (sortMode === "kind") {
    return copy.sort((a, b) => a.kind - b.kind || a.label.localeCompare(b.label));
  }
  return copy.sort((a, b) => {
    const dateA = a.date || "9999-99-99";
    const dateB = b.date || "9999-99-99";
    return dateA.localeCompare(dateB) || a.label.localeCompare(b.label) || a.id - b.id;
  });
}

function FilterBar({
  filters,
  setFilter,
  resetFilters,
  tags,
  kindOptions,
  sortMode,
  setSortMode,
}: {
  filters: Filters;
  setFilter: (key: keyof Filters, value: string) => void;
  resetFilters: () => void;
  tags: Tag[];
  kindOptions: number[];
  sortMode: string;
  setSortMode: (mode: string) => void;
}) {
  return (
    <section className="filters">
      <input
        placeholder="Search"
        list="search-options"
        value={filters.q}
        onChange={(event) => setFilter("q", event.target.value)}
        aria-label="Search works and tags"
      />
      <datalist id="search-options">
        {tags.slice(0, 1000).map((tag) => (
          <option key={`tag-${tag.id}`} value={tag.name} />
        ))}
      </datalist>
      <input
        type="date"
        value={filters.minDate}
        onChange={(event) => setFilter("minDate", event.target.value)}
        aria-label="Minimum date"
      />
      <input
        type="date"
        value={filters.maxDate}
        onChange={(event) => setFilter("maxDate", event.target.value)}
        aria-label="Maximum date"
      />
      <select value={filters.kind} onChange={(event) => setFilter("kind", event.target.value)} aria-label="Kind">
        <option value="">All kinds</option>
        {kindOptions.map((kind) => (
          <option key={kind} value={kind}>
            {kindLabel(kind)}
          </option>
        ))}
      </select>
      <select value={filters.tag} onChange={(event) => setFilter("tag", event.target.value)} aria-label="Tag">
        <option value="">All tags</option>
        {tags.map((tag) => (
          <option key={tag.id} value={tag.id}>
            {tag.name}
          </option>
        ))}
      </select>
      <select value={sortMode} onChange={(event) => setSortMode(event.target.value)} aria-label="Sort">
        <option value="date">Date</option>
        <option value="label">Label</option>
        <option value="kind">Kind</option>
      </select>
      <button type="button" onClick={resetFilters}>
        Reset
      </button>
    </section>
  );
}

export function BrowseView({
  data,
  ratings,
  visible,
  filters,
  sortMode,
  onFiltersChange,
  onSortModeChange,
  onOpen,
  onRate,
}: {
  data: AppData;
  ratings: Ratings;
  visible: CatalogItem[];
  filters: Filters;
  sortMode: string;
  onFiltersChange: (filters: Filters) => void;
  onSortModeChange: (mode: string) => void;
  onOpen: OpenHandler;
  onRate: RateHandler;
}) {
  const kindOptions = useMemo(
    () => [...new Set(data.catalog.map((item) => item.kind))].sort((a, b) => a - b),
    [data],
  );

  function setFilter(key: keyof Filters, value: string) {
    onFiltersChange({ ...filters, [key]: value });
  }

  function resetFilters() {
    onFiltersChange(EMPTY_FILTERS);
    onSortModeChange("date");
  }

  return (
    <>
      <FilterBar
        filters={filters}
        setFilter={setFilter}
        resetFilters={resetFilters}
        tags={data.tags}
        kindOptions={kindOptions}
        sortMode={sortMode}
        setSortMode={onSortModeChange}
      />
      {visible.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Work</th>
                <th className="kind-head">
                  <span className="visually-hidden">Kind</span>
                </th>
                <th>Tags</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} {...rowInteractionProps(item.id, item.label, onOpen)}>
                  <td className="date-cell">{dateLabel(item.date, item.datePrecision)}</td>
                  <td className="label-cell">{item.label}</td>
                  <td className="kind-cell">
                    <KindIcon kind={item.kind} />
                  </td>
                  <td>
                    <TagList entries={tagEntries(item, data)} initialLimit={6} expandable={false} />
                  </td>
                  <td className="rating-cell">
                    <RatingButtons
                      id={item.id}
                      label={item.label}
                      rating={ratings[String(item.id)] || 0}
                      onRate={onRate}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty">No works match the current filters.</div>
      )}
    </>
  );
}
