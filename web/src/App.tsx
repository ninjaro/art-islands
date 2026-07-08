import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { EMPTY_FILTERS, filterWorks, relevanceScores, sortWorks } from "./lib/browse";
import type { Filters } from "./lib/browse";
import { loadAppData } from "./lib/data";
import { buildFeatureIndex } from "./lib/features";
import { loadRatings, saveRatings, toggleRating } from "./lib/ratings";
import type { AppData, RatingValue, Ratings, Settings } from "./lib/types";
import { DEFAULT_SETTINGS } from "./lib/types";
import { FloatingEntityWindows, useEntityWindows } from "./components/windows";
import { BrowseView } from "./views/BrowseView";
import { RecommendationsView } from "./views/RecommendationsView";
import { EvolutionView } from "./views/EvolutionView";
import { IslandsView } from "./views/IslandsView";

type ViewName = "browse" | "recommendations" | "evolution" | "islands";

const VIEWS: { name: ViewName; label: string }[] = [
  { name: "browse", label: "Browse" },
  { name: "recommendations", label: "Recommendations" },
  { name: "evolution", label: "Evolution" },
  { name: "islands", label: "Islands" },
];

export default function App() {
  const [data, setData] = useState<AppData | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [error, setError] = useState("");
  const [view, setView] = useState<ViewName>("browse");
  const [ratings, setRatings] = useState<Ratings>(() => loadRatings());
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortMode, setSortMode] = useState("date");
  // Pagination state lives here so it survives view switches (FR-3.8).
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(0); // 0 = settings default
  const viewScroll = useRef<Partial<Record<ViewName, number>>>({});

  const { windows, openWindow, focusWindow, closeWindow, startDrag } = useEntityWindows();

  useEffect(() => {
    loadAppData()
      .then((loaded) => {
        setData(loaded.data);
        setSettings(loaded.settings);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => saveRatings(ratings), [ratings]);

  // Table scroll preservation across view switches (audit fix carried over).
  function switchView(nextView: ViewName) {
    if (nextView === view) return;
    const scroller = document.querySelector(".table-wrap");
    if (scroller) viewScroll.current[view] = scroller.scrollTop;
    setView(nextView);
  }

  useLayoutEffect(() => {
    const scroller = document.querySelector(".table-wrap");
    if (scroller) scroller.scrollTop = viewScroll.current[view] || 0;
  }, [view]);

  // Reusable weighted feature index, built once per catalog and settings.
  // Rating changes never rebuild it.
  const featureIndex = useMemo(
    () => (data ? buildFeatureIndex(data.domain.works, settings.features) : null),
    [data, settings.features],
  );

  const filtered = useMemo(() => (data ? filterWorks(data.domain, filters) : []), [data, filters]);
  const relevance = useMemo(
    () => (data && featureIndex ? relevanceScores(featureIndex, filtered, filters) : null),
    [data, featureIndex, filtered, filters],
  );
  const visible = useMemo(() => sortWorks(filtered, sortMode, relevance), [filtered, sortMode, relevance]);

  const effectivePageSize = pageSize || settings.browse.defaultPageSize;

  // Changing a filter, search query, or sort mode resets to page 1 (FR-3.6).
  function handleFiltersChange(next: Filters) {
    setFilters(next);
    setPage(1);
  }
  function handleSortModeChange(mode: string) {
    setSortMode(mode);
    setPage(1);
  }
  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  const ratedCount = Object.keys(ratings).length;

  function handleRate(id: number, value: RatingValue) {
    setRatings((current) => toggleRating(current, id, value));
  }

  function clearRatings() {
    if (!ratedCount) return;
    if (window.confirm("Clear all local ratings?")) {
      setRatings({});
    }
  }

  if (error) {
    return (
      <div className="error-panel" role="alert">
        <h2>Data failed to load</h2>
        <p>{error}</p>
        <button type="button" onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    );
  }
  if (!data || !featureIndex) {
    return (
      <div className="loading" role="status">
        Loading catalog…
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Art Islands</h1>
          <div className="count">
            {view === "browse"
              ? `${visible.length.toLocaleString()} of ${data.domain.works.length.toLocaleString()} works`
              : `${data.domain.works.length.toLocaleString()} works`}
          </div>
        </div>
        <nav className="view-tabs" aria-label="Main views">
          {VIEWS.map(({ name, label }) => (
            <button
              key={name}
              type="button"
              className={view === name ? "tab active" : "tab"}
              onClick={() => switchView(name)}
              aria-pressed={view === name}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="rating-summary">
          <span>{ratedCount.toLocaleString()} rated</span>
          <button type="button" className="clear-ratings" disabled={ratedCount === 0} onClick={clearRatings}>
            Clear ratings
          </button>
        </div>
      </header>
      {view === "browse" ? (
        <BrowseView
          domain={data.domain}
          ratings={ratings}
          visible={visible}
          filters={filters}
          sortMode={sortMode}
          page={page}
          pageSize={effectivePageSize}
          pageSizeOptions={settings.browse.pageSizeOptions}
          onFiltersChange={handleFiltersChange}
          onSortModeChange={handleSortModeChange}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
          onOpen={openWindow}
          onRate={handleRate}
        />
      ) : view === "recommendations" ? (
        <RecommendationsView
          domain={data.domain}
          index={featureIndex}
          ratings={ratings}
          settings={settings}
          onOpen={openWindow}
          onRate={handleRate}
        />
      ) : view === "evolution" ? (
        <EvolutionView
          data={data}
          domain={data.domain}
          index={featureIndex}
          settings={settings}
          onOpen={openWindow}
        />
      ) : (
        <IslandsView
          domain={data.domain}
          index={featureIndex}
          ratings={ratings}
          settings={settings}
          onOpen={openWindow}
          onRate={handleRate}
        />
      )}
      <FloatingEntityWindows
        windows={windows}
        domain={data.domain}
        ratings={ratings}
        onFocus={focusWindow}
        onClose={closeWindow}
        onDragStart={startDrag}
        onRate={handleRate}
      />
    </div>
  );
}
