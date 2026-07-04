import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { loadAppData } from "./lib/data";
import { loadRatings, saveRatings, toggleRating } from "./lib/ratings";
import { buildTagIndex } from "./lib/tagIndex";
import type { AppData, RatingValue, Ratings, Settings } from "./lib/types";
import { DEFAULT_SETTINGS } from "./lib/types";
import { FloatingEntityWindows, useEntityWindows } from "./components/windows";
import { BrowseView, EMPTY_FILTERS, filterCatalog, sortCatalog } from "./views/BrowseView";
import type { Filters } from "./views/BrowseView";
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

  // Reusable IDF tag index, built once per catalog.
  const tagIndex = useMemo(() => (data ? buildTagIndex(data.catalog) : null), [data]);

  const visible = useMemo(
    () => (data ? sortCatalog(filterCatalog(data, filters), sortMode) : []),
    [data, filters, sortMode],
  );

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

  if (error) return <div className="error">{error}</div>;
  if (!data || !tagIndex) return <div className="loading">Loading…</div>;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Art Islands</h1>
          <div className="count">
            {view === "browse"
              ? `${visible.length.toLocaleString()} of ${data.catalog.length.toLocaleString()} works`
              : `${data.catalog.length.toLocaleString()} works`}
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
          data={data}
          ratings={ratings}
          visible={visible}
          filters={filters}
          sortMode={sortMode}
          onFiltersChange={setFilters}
          onSortModeChange={setSortMode}
          onOpen={openWindow}
          onRate={handleRate}
        />
      ) : view === "recommendations" ? (
        <RecommendationsView data={data} ratings={ratings} settings={settings} onOpen={openWindow} onRate={handleRate} />
      ) : view === "evolution" ? (
        <EvolutionView data={data} tagIndex={tagIndex} settings={settings} onOpen={openWindow} />
      ) : (
        <IslandsView
          data={data}
          tagIndex={tagIndex}
          ratings={ratings}
          settings={settings}
          onOpen={openWindow}
          onRate={handleRate}
        />
      )}
      <FloatingEntityWindows
        windows={windows}
        data={data}
        ratings={ratings}
        onFocus={focusWindow}
        onClose={closeWindow}
        onDragStart={startDrag}
        onRate={handleRate}
      />
    </div>
  );
}
