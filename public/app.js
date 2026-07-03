const h = React.createElement;
const RATINGS_KEY = "art-islands-ratings-v1";

const KIND_LABELS = {
  0: "unknown",
  1: "film",
  2: "music release",
  3: "person",
  4: "group",
  5: "organization",
  6: "video game",
  7: "work",
  8: "genre",
};

const SCORE_API = window.ArtIslandsRecommendations;

function loadJson(path) {
  return fetch(path).then((response) => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  });
}

function loadSettings() {
  return fetch("data/settings.json")
    .then((response) => response.ok ? response.json() : SCORE_API.DEFAULTS)
    .catch(() => SCORE_API.DEFAULTS);
}

function dateLabel(date, precision) {
  if (!date) return "";
  if (precision === 1) return date.slice(0, 4);
  if (precision === 2) return date.slice(0, 7);
  return date;
}

function imageUrl(image) {
  if (!image) return "";
  return `https://commons.wikimedia.org/wiki/Special:Redirect/file/${encodeURIComponent(image)}`;
}

function externalUrl(ref) {
  if (!ref) return "";
  const [kind, value] = ref;
  if (kind === "wikidata") return `https://www.wikidata.org/wiki/${value}`;
  if (kind === "imdb") return `https://www.imdb.com/title/${value}/`;
  if (kind === "tmdb") return `https://www.themoviedb.org/movie/${value}`;
  if (kind === "musicbrainz") return `https://musicbrainz.org/release-group/${value}`;
  if (kind === "discogs") return `https://www.discogs.com/release/${value}`;
  return "";
}

function loadRatings() {
  try {
    const raw = JSON.parse(localStorage.getItem(RATINGS_KEY) || "{}");
    const ratings = {};
    for (const [id, value] of Object.entries(raw)) {
      if (value === 1 || value === -1) ratings[id] = value;
    }
    return ratings;
  } catch {
    return {};
  }
}

function saveRatings(ratings) {
  localStorage.setItem(RATINGS_KEY, JSON.stringify(ratings));
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function clampWindowPosition(x, y, width, height) {
  const margin = 8;
  const maxX = Math.max(margin, window.innerWidth - width - margin);
  const maxY = Math.max(margin, window.innerHeight - height - margin);
  return {
    x: clamp(x, margin, maxX),
    y: clamp(y, margin, maxY),
  };
}

function isNarrowScreen() {
  return window.matchMedia("(max-width: 720px)").matches;
}

function App() {
  const [data, setData] = React.useState(null);
  const [settings, setSettings] = React.useState(SCORE_API.DEFAULTS);
  const [error, setError] = React.useState("");
  const [view, setView] = React.useState("browse");
  const [ratings, setRatings] = React.useState(loadRatings);
  const [filters, setFilters] = React.useState({
    q: "",
    minDate: "",
    maxDate: "",
    kind: "",
    tag: "",
  });
  const [sortMode, setSortMode] = React.useState("date");
  const [windows, setWindows] = React.useState([]);
  const zIndex = React.useRef(30);
  const drag = React.useRef(null);

  React.useEffect(() => {
    Promise.all([
      loadJson("data/catalog.json"),
      loadJson("data/tags.json"),
      loadJson("data/entities-lookup.json"),
      loadSettings(),
    ]).then(([catalog, tags, lookup, loadedSettings]) => {
      const tagById = new Map(tags.map((tag) => [tag.id, tag]));
      const catalogById = new Map(catalog.map((item) => [item.id, item]));
      setSettings(loadedSettings);
      setData({ catalog, tags, tagById, lookup, catalogById });
    }).catch((err) => setError(err.message));
  }, []);

  React.useEffect(() => saveRatings(ratings), [ratings]);

  React.useEffect(() => {
    function onMove(event) {
      const active = drag.current;
      if (!active) return;
      event.preventDefault();
      const next = clampWindowPosition(
        event.clientX - active.offsetX,
        event.clientY - active.offsetY,
        active.width,
        active.height,
      );
      setWindows((current) => current.map((win) => (
        win.id === active.id ? { ...win, x: next.x, y: next.y } : win
      )));
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

  if (error) return h("div", { className: "error" }, error);
  if (!data) return h("div", { className: "loading" }, "Loading...");

  const visible = sortCatalog(filterCatalog(data, filters), sortMode);
  const kindOptions = [...new Set(data.catalog.map((item) => item.kind))]
    .sort((a, b) => a - b);
  const ratedCount = Object.keys(ratings).length;

  function setFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function resetFilters() {
    setFilters({ q: "", minDate: "", maxDate: "", kind: "", tag: "" });
    setSortMode("date");
  }

  function nextZ() {
    zIndex.current += 1;
    return zIndex.current;
  }

  function focusWindow(id) {
    setWindows((current) => current.map((win) => (
      win.id === id ? { ...win, z: nextZ() } : win
    )));
  }

  function openWindow(id) {
    const index = windows.length;
    setWindows((current) => {
      const existing = current.find((win) => win.id === id);
      if (existing) {
        return current.map((win) => (
          win.id === id ? { ...win, z: nextZ() } : win
        ));
      }
      const width = 580;
      const height = 560;
      const pos = clampWindowPosition(56 + index * 28, 88 + index * 24, width, height);
      return [
        ...current,
        { id, x: pos.x, y: pos.y, z: nextZ() },
      ];
    });
  }

  function closeWindow(id) {
    setWindows((current) => current.filter((win) => win.id !== id));
  }

  function startDrag(event, win) {
    if (isNarrowScreen()) return;
    if (event.button !== 0) return;
    const panel = event.currentTarget.closest(".entity-window");
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
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function setRating(id, value) {
    setRatings((current) => {
      const key = String(id);
      const next = { ...current };
      if (next[key] === value) {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  }

  function clearRatings() {
    if (!ratedCount) return;
    if (window.confirm("Clear all local ratings?")) {
      setRatings({});
    }
  }

  return h("div", { className: "app" },
    h("header", { className: "topbar" },
      h("div", { className: "brand" },
        h("h1", null, "Art Islands"),
        h("div", { className: "count" },
          `${visible.length.toLocaleString()} of ${data.catalog.length.toLocaleString()} works`
        )
      ),
      h("nav", { className: "view-tabs", "aria-label": "Main views" },
        h(TabButton, { active: view === "browse", onClick: () => setView("browse") }, "Browse"),
        h(TabButton, { active: view === "recommendations", onClick: () => setView("recommendations") }, "Recommendations")
      ),
      h("div", { className: "rating-summary" },
        h("span", null, `${ratedCount.toLocaleString()} rated`),
        h("button", {
          className: "clear-ratings",
          disabled: ratedCount === 0,
          onClick: clearRatings,
        }, "Clear ratings")
      )
    ),
    view === "browse" ? h(React.Fragment, null,
      h(FilterBar, {
        filters,
        setFilter,
        resetFilters,
        tags: data.tags,
        kindOptions,
        sortMode,
        setSortMode,
      }),
      h(CatalogTable, {
        items: visible,
        data,
        ratings,
        onOpen: openWindow,
        onRate: setRating,
      })
    ) : h(RecommendationsView, {
      data,
      ratings,
      settings,
      onOpen: openWindow,
      onRate: setRating,
    }),
    h(FloatingEntityWindows, {
      windows,
      data,
      ratings,
      onFocus: focusWindow,
      onClose: closeWindow,
      onDragStart: startDrag,
      onRate: setRating,
    })
  );
}

function TabButton({ active, onClick, children }) {
  return h("button", {
    className: active ? "tab active" : "tab",
    onClick,
    "aria-pressed": active,
  }, children);
}

function FilterBar({ filters, setFilter, resetFilters, tags, kindOptions, sortMode, setSortMode }) {
  return h("section", { className: "filters" },
    h("input", {
      placeholder: "Search",
      list: "search-options",
      value: filters.q,
      onChange: (event) => setFilter("q", event.target.value),
    }),
    h("datalist", { id: "search-options" },
      tags.slice(0, 1000).map((tag) => h("option", { key: `tag-${tag.id}`, value: tag.name }))
    ),
    h("input", {
      type: "date",
      value: filters.minDate,
      onChange: (event) => setFilter("minDate", event.target.value),
      "aria-label": "Minimum date",
    }),
    h("input", {
      type: "date",
      value: filters.maxDate,
      onChange: (event) => setFilter("maxDate", event.target.value),
      "aria-label": "Maximum date",
    }),
    h("select", {
      value: filters.kind,
      onChange: (event) => setFilter("kind", event.target.value),
      "aria-label": "Kind",
    },
      h("option", { value: "" }, "All kinds"),
      kindOptions.map((kind) => h("option", { key: kind, value: kind }, KIND_LABELS[kind] || kind))
    ),
    h("select", {
      value: filters.tag,
      onChange: (event) => setFilter("tag", event.target.value),
      "aria-label": "Tag",
    },
      h("option", { value: "" }, "All tags"),
      tags.map((tag) => h("option", { key: tag.id, value: tag.id }, tag.name))
    ),
    h("select", {
      value: sortMode,
      onChange: (event) => setSortMode(event.target.value),
      "aria-label": "Sort",
    },
      h("option", { value: "date" }, "Date"),
      h("option", { value: "label" }, "Label"),
      h("option", { value: "kind" }, "Kind")
    ),
    h("button", { onClick: resetFilters }, "Reset")
  );
}

function CatalogTable({ items, data, ratings, onOpen, onRate }) {
  if (!items.length) return h("div", { className: "empty" }, "No works match the current filters.");
  return h("div", { className: "table-wrap" },
    h("table", null,
      h("thead", null,
        h("tr", null,
          h("th", null, "Date"),
          h("th", null, "Work"),
          h("th", { className: "kind-head" }, h("span", { className: "visually-hidden" }, "Kind")),
          h("th", null, "Tags"),
          h("th", null, "Rating")
        )
      ),
      h("tbody", null,
        items.map((item) => h("tr", { key: item.id, onClick: () => onOpen(item.id) },
          h("td", { className: "date-cell" }, dateLabel(item.date, item.datePrecision)),
          h("td", { className: "label-cell" }, item.label),
          h("td", { className: "kind-cell" }, h(KindIcon, { kind: item.kind })),
          h("td", null, h(TagList, {
            entries: tagEntries(item, data),
            initialLimit: 6,
            expandable: false,
          })),
          h("td", { className: "rating-cell" }, h(RatingButtons, {
            id: item.id,
            label: item.label,
            rating: ratings[String(item.id)] || 0,
            onRate,
          }))
        ))
      )
    )
  );
}

function RecommendationsView({ data, ratings, settings, onOpen, onRate }) {
  const likedCount = Object.values(ratings).filter((value) => value === 1).length;
  if (!likedCount) {
    return h("section", { className: "empty" }, "Like several works first to build recommendations.");
  }

  const scored = SCORE_API.scoreRecommendations(data.catalog, ratings, settings);
  if (!scored.length) {
    return h("section", { className: "empty" }, "No unrated works have positive liked-tag evidence yet.");
  }

  return h("section", { className: "recommendation-view" },
    h("div", { className: "recommendation-head" },
      h("h2", null, "Recommendations"),
      h("span", null, `${scored.length.toLocaleString()} shown`)
    ),
    h("div", { className: "table-wrap recommendation-table" },
      h("table", null,
        h("thead", null,
          h("tr", null,
            h("th", null, "Score"),
            h("th", null, "Date"),
            h("th", null, "Work"),
            h("th", { className: "kind-head" }, h("span", { className: "visually-hidden" }, "Kind")),
            h("th", null, "Why"),
            h("th", null, "Rating")
          )
        ),
        h("tbody", null,
          scored.map((result) => h("tr", { key: result.item.id, onClick: () => onOpen(result.item.id) },
            h("td", { className: "score-cell" }, result.score.toFixed(2)),
            h("td", { className: "date-cell" }, dateLabel(result.item.date, result.item.datePrecision)),
            h("td", { className: "label-cell" }, result.item.label),
            h("td", { className: "kind-cell" }, h(KindIcon, { kind: result.item.kind })),
            h("td", { className: "why-cell" }, SCORE_API.explanation(result)),
            h("td", { className: "rating-cell" }, h(RatingButtons, {
              id: result.item.id,
              label: result.item.label,
              rating: ratings[String(result.item.id)] || 0,
              onRate,
            }))
          ))
        )
      )
    )
  );
}

function FloatingEntityWindows({ windows, data, ratings, onFocus, onClose, onDragStart, onRate }) {
  return h(React.Fragment, null,
    windows.map((win) => {
      const item = data.catalogById.get(win.id);
      if (!item) return null;
      return h("article", {
        key: win.id,
        className: "entity-window",
        style: { left: `${win.x}px`, top: `${win.y}px`, zIndex: win.z },
        onPointerDown: () => onFocus(win.id),
      },
        h("header", {
          className: "window-header",
          onPointerDown: (event) => onDragStart(event, win),
        },
          h("div", { className: "window-title" },
            h("strong", null, item.label),
            h("span", null, [dateLabel(item.date, item.datePrecision), KIND_LABELS[item.kind] || "unknown"].filter(Boolean).join(" / "))
          ),
          h("button", {
            className: "icon-button close-button",
            onClick: (event) => {
              event.stopPropagation();
              onClose(win.id);
            },
            title: "Close",
            "aria-label": `Close ${item.label}`,
          }, h(SvgIcon, { name: "close", title: "Close" }))
        ),
        h(EntityDetails, {
          item,
          data,
          rating: ratings[String(item.id)] || 0,
          onRate,
        })
      );
    })
  );
}

function EntityDetails({ item, data, rating, onRate }) {
  const image = imageUrl(item.image);
  const refs = item.refs || [];
  return h("div", { className: "entity-body" },
    image ? h("img", { className: "entity-image", src: image, alt: item.label }) : h("div", { className: "entity-image placeholder" }),
    h("div", { className: "entity-main" },
      h("div", { className: "entity-meta" },
        h(KindIcon, { kind: item.kind }),
        h("span", null, dateLabel(item.date, item.datePrecision) || "undated")
      ),
      h(RatingButtons, {
        id: item.id,
        label: item.label,
        rating,
        onRate,
      }),
      h(TagList, {
        entries: tagEntries(item, data),
        initialLimit: 12,
        expandable: true,
      }),
      refs.length ? h("div", { className: "ref-list" },
        refs.map((ref) => {
          const url = externalUrl(ref);
          const label = ref[0];
          return url ? h("a", {
            key: `${ref[0]}-${ref[1]}`,
            href: url,
            target: "_blank",
            rel: "noreferrer",
          }, label) : h("span", { key: `${ref[0]}-${ref[1]}` }, label);
        })
      ) : null
    )
  );
}

function RatingButtons({ id, label, rating, onRate }) {
  return h("div", { className: "rating-buttons", onClick: (event) => event.stopPropagation() },
    h("button", {
      className: rating === 1 ? "icon-button rating active like" : "icon-button rating like",
      onClick: () => onRate(id, 1),
      title: `Like ${label}`,
      "aria-label": `Like ${label}`,
      "aria-pressed": rating === 1,
    }, h(SvgIcon, { name: "like", title: `Like ${label}` })),
    h("button", {
      className: rating === -1 ? "icon-button rating active dislike" : "icon-button rating dislike",
      onClick: () => onRate(id, -1),
      title: `Dislike ${label}`,
      "aria-label": `Dislike ${label}`,
      "aria-pressed": rating === -1,
    }, h(SvgIcon, { name: "dislike", title: `Dislike ${label}` }))
  );
}

function TagList({ entries, initialLimit, expandable }) {
  const [expanded, setExpanded] = React.useState(false);
  const limited = expanded ? entries : entries.slice(0, initialLimit);
  const overflow = entries.length > initialLimit;

  return h("div", { className: expanded ? "tag-block expanded" : "tag-block" },
    h("div", { className: "chips" },
      limited.map(({ tag, weight, polarity }) => h("span", {
        key: tag.id,
        className: `chip ${polarity > 0 ? "positive" : polarity < 0 ? "negative" : ""}`,
        title: tag.description || "",
      }, `${tag.name} ${weight}`)),
      !expandable && overflow ? h("span", { className: "chip more" }, `+${entries.length - initialLimit}`) : null
    ),
    expandable && overflow ? h("button", {
      className: "tag-toggle",
      onClick: () => setExpanded((value) => !value),
    }, expanded ? "Collapse" : `Show all (${entries.length})`) : null
  );
}

function tagEntries(item, data) {
  return (item.tags || [])
    .map(([tagId, weight, polarity]) => ({ tag: data.tagById.get(tagId), weight, polarity }))
    .filter((entry) => entry.tag)
    .sort((a, b) => b.weight - a.weight || a.tag.name.localeCompare(b.tag.name));
}

function filterCatalog(data, filters) {
  const q = filters.q.trim().toLowerCase();
  return data.catalog.filter((item) => {
    if (filters.kind && String(item.kind) !== filters.kind) return false;
    if (filters.minDate && (!item.date || item.date < filters.minDate)) return false;
    if (filters.maxDate && (!item.date || item.date > filters.maxDate)) return false;
    if (filters.tag && !item.tags.some(([tagId]) => String(tagId) === filters.tag)) return false;
    if (!q) return true;

    const tagHit = item.tags.some(([tagId]) => {
      const tag = data.tagById.get(tagId);
      return tag && tag.name.toLowerCase().includes(q);
    });
    return item.label.toLowerCase().includes(q) || tagHit;
  });
}

function sortCatalog(items, sortMode) {
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

function KindIcon({ kind }) {
  const label = KIND_LABELS[kind] || "unknown";
  const icon = kind === 1
    ? "film"
    : kind === 2
      ? "music"
      : kind === 6
        ? "game"
        : kind === 7
          ? "book"
          : "unknown";
  return h("span", {
    className: "kind-icon",
    title: label,
    "aria-label": label,
  }, h(SvgIcon, { name: icon, title: label }));
}

function SvgIcon({ name, title }) {
  const common = {
    viewBox: "0 0 24 24",
    width: 18,
    height: 18,
    role: "img",
    "aria-label": title,
    focusable: "false",
  };
  return h("svg", common,
    h("title", null, title),
    iconNodes(name)
  );
}

function iconNodes(name) {
  const lineProps = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    strokeWidth: 2,
  };
  if (name === "close") {
    return [
      h("path", { key: "a", ...lineProps, d: "M18 6 6 18" }),
      h("path", { key: "b", ...lineProps, d: "m6 6 12 12" }),
    ];
  }
  if (name === "like") {
    return [
      h("path", { key: "a", ...lineProps, d: "M7 10v11" }),
      h("path", { key: "b", ...lineProps, d: "M15 5.5 14 10h5.5a2 2 0 0 1 2 2.4l-1.2 6a3 3 0 0 1-3 2.6H7l-4-1V10h4l5-7a2 2 0 0 1 3 2.5Z" }),
    ];
  }
  if (name === "dislike") {
    return [
      h("path", { key: "a", ...lineProps, d: "M7 14V3" }),
      h("path", { key: "b", ...lineProps, d: "M15 18.5 14 14h5.5a2 2 0 0 0 2-2.4l-1.2-6a3 3 0 0 0-3-2.6H7L3 4v10h4l5 7a2 2 0 0 0 3-2.5Z" }),
    ];
  }
  if (name === "film") {
    return [
      h("rect", { key: "a", ...lineProps, x: 3, y: 4, width: 18, height: 16, rx: 2 }),
      h("path", { key: "b", ...lineProps, d: "M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" }),
    ];
  }
  if (name === "music") {
    return [
      h("path", { key: "a", ...lineProps, d: "M9 18V5l10-2v13" }),
      h("circle", { key: "b", ...lineProps, cx: 6, cy: 18, r: 3 }),
      h("circle", { key: "c", ...lineProps, cx: 16, cy: 16, r: 3 }),
    ];
  }
  if (name === "game") {
    return [
      h("path", { key: "a", ...lineProps, d: "M6 12h4m-2-2v4" }),
      h("path", { key: "b", ...lineProps, d: "M15 13h.01M18 11h.01" }),
      h("path", { key: "c", ...lineProps, d: "M5 8h14a3 3 0 0 1 3 3v4a4 4 0 0 1-7 2.5L13.5 16h-3L9 17.5A4 4 0 0 1 2 15v-4a3 3 0 0 1 3-3Z" }),
    ];
  }
  if (name === "book") {
    return [
      h("path", { key: "a", ...lineProps, d: "M3 5.5A2.5 2.5 0 0 1 5.5 3H21v16H6a3 3 0 0 0-3 3Z" }),
      h("path", { key: "b", ...lineProps, d: "M3 5.5v14A2.5 2.5 0 0 1 5.5 17H21" }),
    ];
  }
  return [
    h("circle", { key: "a", ...lineProps, cx: 12, cy: 12, r: 9 }),
    h("path", { key: "b", ...lineProps, d: "M9.5 9a2.5 2.5 0 0 1 4.7 1.2c0 1.8-2.2 2-2.2 3.8" }),
    h("path", { key: "c", ...lineProps, d: "M12 17h.01" }),
  ];
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
