import { useMemo } from "react";
import { EMPTY_FILTERS, hasRelevanceContext } from "../lib/browse";
import type { Filters } from "../lib/browse";
import type { DomainModel, WorkViewModel } from "../lib/domain";
import { dateLabel } from "../lib/format";
import { paginate } from "../lib/pagination";
import type { Ratings } from "../lib/types";
import {
  ConceptChips,
  KindIcon,
  PaginationControls,
  RatingButtons,
  rowInteractionProps,
} from "../components/common";
import type { OpenHandler, RateHandler } from "../components/common";

function FilterBar({
  domain,
  filters,
  setFilter,
  resetFilters,
  sortMode,
  setSortMode,
}: {
  domain: DomainModel;
  filters: Filters;
  setFilter: (key: keyof Filters, value: string) => void;
  resetFilters: () => void;
  sortMode: string;
  setSortMode: (mode: string) => void;
}) {
  const conceptOptions = useMemo(
    () => [...domain.conceptById.values()].sort((a, b) => a.label.localeCompare(b.label)),
    [domain],
  );
  const relevanceAvailable = hasRelevanceContext(filters);
  return (
    <section className="filters sticky">
      <input
        type="search"
        placeholder="Search works, concepts, people"
        list="search-options"
        value={filters.q}
        onChange={(event) => setFilter("q", event.target.value)}
        aria-label="Search works, concepts, and contributors"
      />
      <datalist id="search-options">
        {conceptOptions.slice(0, 1000).map((concept) => (
          <option key={`concept-${concept.id}`} value={concept.label} />
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
      <select value={filters.type} onChange={(event) => setFilter("type", event.target.value)} aria-label="Type">
        <option value="">All types</option>
        {domain.typeOptions.map((option) => (
          <option key={option.code} value={option.code}>
            {option.label} ({option.count})
          </option>
        ))}
      </select>
      <select
        value={filters.conceptId}
        onChange={(event) => setFilter("conceptId", event.target.value)}
        aria-label="Concept"
      >
        <option value="">All concepts</option>
        {conceptOptions.map((concept) => (
          <option key={concept.id} value={concept.id}>
            {concept.label}
          </option>
        ))}
      </select>
      <select value={sortMode} onChange={(event) => setSortMode(event.target.value)} aria-label="Sort">
        <option value="date">Date</option>
        <option value="label">Label</option>
        <option value="kind">Kind</option>
        <option value="relevance" disabled={!relevanceAvailable}>
          Relevance
        </option>
      </select>
      <button type="button" onClick={resetFilters}>
        Clear all
      </button>
    </section>
  );
}

function ActiveFilterChips({
  domain,
  filters,
  setFilter,
}: {
  domain: DomainModel;
  filters: Filters;
  setFilter: (key: keyof Filters, value: string) => void;
}) {
  const chips: Array<{ key: keyof Filters; label: string }> = [];
  if (filters.q.trim()) chips.push({ key: "q", label: `Search: ${filters.q.trim()}` });
  if (filters.minDate) chips.push({ key: "minDate", label: `From ${filters.minDate}` });
  if (filters.maxDate) chips.push({ key: "maxDate", label: `Until ${filters.maxDate}` });
  if (filters.type) {
    const option = domain.typeOptions.find((entry) => entry.code === filters.type);
    chips.push({ key: "type", label: `Type: ${option?.label ?? filters.type}` });
  }
  if (filters.conceptId) {
    const concept = domain.conceptById.get(Number(filters.conceptId));
    chips.push({ key: "conceptId", label: `Concept: ${concept?.label ?? filters.conceptId}` });
  }
  if (!chips.length) return null;
  return (
    <div className="filter-chips" aria-label="Active filters">
      {chips.map((chip) => (
        <span key={chip.key} className="chip filter-chip">
          {chip.label}
          <button
            type="button"
            className="chip-remove"
            onClick={() => setFilter(chip.key, "")}
            aria-label={`Remove filter ${chip.label}`}
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

export function BrowseView({
  domain,
  ratings,
  visible,
  filters,
  sortMode,
  page,
  pageSize,
  pageSizeOptions,
  onFiltersChange,
  onSortModeChange,
  onPageChange,
  onPageSizeChange,
  onOpen,
  onRate,
}: {
  domain: DomainModel;
  ratings: Ratings;
  visible: WorkViewModel[];
  filters: Filters;
  sortMode: string;
  page: number;
  pageSize: number;
  pageSizeOptions: number[];
  onFiltersChange: (filters: Filters) => void;
  onSortModeChange: (mode: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onOpen: OpenHandler;
  onRate: RateHandler;
}) {
  function setFilter(key: keyof Filters, value: string) {
    onFiltersChange({ ...filters, [key]: value });
  }

  function resetFilters() {
    onFiltersChange(EMPTY_FILTERS);
    onSortModeChange("date");
  }

  // Only the current page of rows is mounted in the DOM (FR-3.2).
  const pageResult = paginate(visible, page, pageSize);

  const pagination = (
    <PaginationControls
      page={pageResult.page}
      pageCount={pageResult.pageCount}
      totalItems={pageResult.totalItems}
      pageSize={pageSize}
      pageSizeOptions={pageSizeOptions}
      onPageChange={onPageChange}
      onPageSizeChange={onPageSizeChange}
    />
  );

  return (
    <>
      <FilterBar
        domain={domain}
        filters={filters}
        setFilter={setFilter}
        resetFilters={resetFilters}
        sortMode={sortMode}
        setSortMode={onSortModeChange}
      />
      <ActiveFilterChips domain={domain} filters={filters} setFilter={setFilter} />
      {visible.length ? (
        <>
          {pagination}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Work</th>
                  <th className="kind-head">
                    <span className="visually-hidden">Kind</span>
                  </th>
                  <th>Concepts</th>
                  <th>Rating</th>
                </tr>
              </thead>
              <tbody>
                {pageResult.pageItems.map((work) => (
                  <tr key={work.id} {...rowInteractionProps(work.id, work.label, onOpen)}>
                    <td className="date-cell">
                      {work.primaryDate ? dateLabel(work.primaryDate.value, work.primaryDate.precision) : ""}
                    </td>
                    <td className="label-cell">{work.label}</td>
                    <td className="kind-cell">
                      <KindIcon broadKind={work.broadKind} label={work.typeLabel} />
                    </td>
                    <td>
                      <ConceptChips concepts={work.concepts} limit={6} />
                    </td>
                    <td className="rating-cell">
                      <RatingButtons
                        id={work.id}
                        label={work.label}
                        rating={ratings[String(work.id)] || 0}
                        onRate={onRate}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pagination}
        </>
      ) : (
        <div className="empty">No works match the current filters.</div>
      )}
    </>
  );
}
