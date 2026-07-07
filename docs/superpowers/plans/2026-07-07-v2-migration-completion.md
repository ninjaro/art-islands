# Art Islands V2 Migration Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the V2 domain exports the canonical data source of the Art Islands frontend, with one documented weight/polarity feature model shared by Python and TypeScript, bounded explainable graphs, paginated browse, rich work cards, and Git LFS storage for the SQLite database.

**Architecture:** A Python CLI (`src/art_islands/`) owns `data/art-islands.sqlite` and writes static JSON to `public/data/` (legacy) and `public/data/v2/`. The React/Vite app (`web/src/`) loads those files at startup. This plan adds a normalized frontend domain layer (`domain.ts`), a shared feature/scoring layer (`features.ts` + `features.py` verified by golden fixtures), rewires Recommendations/Islands/Evolution onto it, and finishes the UI (pagination, work cards, edge evidence, responsive/accessible polish). No backend is introduced.

**Tech Stack:** Python 3.11+ stdlib only, sqlite3, pytest; TypeScript 5 / React 18 / Vite 6 / vitest 3 / Playwright; @xyflow/react 12, d3-hierarchy, d3-force; Git LFS.

## Global Constraints (from `instructions_v2.md` — read it for full detail)

- Work starts from the `migration` branch; create implementation branch from it. Never discard existing migration work.
- Static app only — no mandatory backend, no fake server-side pagination.
- No all-pairs similarity loops anywhere; candidate generation must go through inverted indexes.
- Deterministic outputs for identical data and settings (explicit tie-breaks everywhere).
- People/groups/organizations must NEVER be Evolution nodes; one-hop feature inheritance only.
- A negative final similarity must never create an inferred graph edge.
- Date/Label/Kind sorts stay literal; only "Relevance" uses feature scoring.
- Missing optional V2 data must not crash the app; missing required V2 files must fail with a clear message.
- Do not rewrite git history (LFS starts at the migration branch onward).
- No raw JSON or internal numeric IDs shown to users.
- Default page size 50; options 25/50/100.
- Suggested settings defaults (section 6 of spec) are the canonical starting values.
- Validation commands that must pass at the end:
  ```sh
  .venv/bin/python -m pytest tests -q
  npm run typecheck
  npm run test:unit
  npm run build
  npm run test:e2e
  ```

## Environment notes (verified on this machine)

- Playwright reuses installed system Chrome locally (`channel: "chrome"` in `playwright.config.ts`); CDN downloads are blocked. `vite preview` needs `--host 127.0.0.1` (already configured).
- `git-lfs` is NOT installed locally yet (`git lfs version` fails). Task 1 installs it.
- The venv path is `.venv/`; if missing, create per README: `python -m venv .venv && .venv/bin/pip install -e . pytest`.
- Real-data facts you may rely on: works=2955 (68 undated); work types: film 1779, music_album 866, other_creative_work 297, television_series 12, comics 1; entityConcepts weights 0–100 with polarity ∈ {0,-1} (10 negatives); relations types incl. cast_member, director, screenwriter, producer, composer, music_artist, record_label, production_company, distributor, publisher, author, creator, voice_actor, lyricist, performer; work↔work relations: adapted_from 21, influenced_by 3, influenced 1; duration measurements use unit `"seconds"`; advisories have `categoryId`, `intensity` 0–100, `uncertainty`, mostly-null `severity`.

## File structure map

**Create**
- `docs/decisions/0001-sqlite-git-lfs.md` — ADR (Task 1)
- `.gitattributes` — LFS tracking (Task 1)
- `docs/feature-model.md` — canonical feature semantics, single source of truth (Task 5)
- `web/src/lib/domain.ts` + `web/src/lib/domain.test.ts` — normalized view models (Task 4)
- `web/src/lib/features.ts` + `web/src/lib/features.test.ts` — TS feature model (Task 5)
- `src/art_islands/features.py` + `tests/test_features.py` — Python feature model (Task 6)
- `tools/generate_feature_golden.py` + `shared/fixtures/feature-golden.json` — golden fixtures (Task 6)
- `web/src/lib/features.golden.test.ts` — TS side of golden verification (Task 6)
- `web/src/lib/pagination.ts` + `web/src/lib/pagination.test.ts` (Task 9)
- `web/src/components/WorkDetails.tsx` — work card body (Task 15)
- `e2e/browse.spec.ts`, `e2e/workcard.spec.ts` (Task 20)

**Modify (main ones)**
- `src/art_islands/v2.py` (export gaps + validation), `src/art_islands/model.py` (settings), `src/art_islands/evolution.py` (V2 features + evidence), `src/art_islands/cli.py` (quick_check)
- `web/src/lib/types.ts`, `data.ts`, `recommendations.ts`, `islands.ts`, `evolution.ts`, `evolutionLayout.ts`, `format.ts`
- `web/src/App.tsx`, all four views, `web/src/components/{common,windows,icons}.tsx`, `web/src/styles.css`
- `data/settings.json`, `.github/workflows/{ci,pages,data-batch}.yml`, `README.md`, `e2e/*`
- **Delete at the end:** `web/src/lib/tagIndex.ts` and legacy types/loads (Task 21)

**Interface conventions used throughout this plan** (defined once here; every task's "Consumes/Produces" refers to these):
- Feature keys: `concept:<conceptId>` (direct), `entity:<entityId>` (contributor/organization, one hop), `advisory:<categoryId>` (content guide).
- `WeightedFeature { key, label, value, source, category?, sourceEntityId?, relationType? }` where `source ∈ "direct-concept" | "contributor" | "organization" | "content-guide"`.
- `EdgeFactor { id, label, contribution, source, category?, relationType? }`.
- `EdgeEvidence { score, sharedFeatureCount, topFactors: EdgeFactor[] }`.
- Base value formula (both languages, documented in `docs/feature-model.md`):
  `clamp(weight/100, 0, 1) × (polarity < 0 ? -1 : +1) × sourceMultiplier`; final value = base × IDF where `IDF(key) = ln(1 + N/df(key))` over catalogued works.

---

## Task 0: Branch + baseline

**Files:** none (git only)

- [ ] **Step 1: Create the implementation branch from migration**

```bash
cd /Users/mevologodskiy/Documents/projects/art-islands
git checkout migration && git pull --ff-only origin migration 2>/dev/null || true
git checkout -b v2-completion
```

- [ ] **Step 2: Verify the baseline is green before changing anything**

```bash
.venv/bin/python -m pytest tests -q && npm run typecheck && npm run test:unit && npm run build
```
Expected: all pass. If `.venv` is missing: `python3 -m venv .venv && .venv/bin/pip install -e . pytest`.

---

## Task 1: Git LFS decision + implementation (FR-2)

**Files:**
- Create: `docs/decisions/0001-sqlite-git-lfs.md`
- Create: `.gitattributes`
- Modify: `.github/workflows/ci.yml`, `.github/workflows/pages.yml`, `.github/workflows/data-batch.yml` (checkout `lfs: true` + pointer validation)
- Modify: `README.md` (setup docs)

**Interfaces:** none consumed; produces an LFS-tracked `data/art-islands.sqlite` that later tasks' exports read normally.

- [ ] **Step 1: Measure and record the real numbers**

```bash
ls -l data/art-islands.sqlite
git rev-list --all --objects -- data/art-islands.sqlite | awk '{print $1}' | git cat-file --batch-check='%(objectsize:disk) %(objectsize)'
du -sh .git
```
Already measured on 2026-07-07: file 76,910,592 B (~73 MiB); 3 blob versions in history, uncompressed 13.1/32.5/76.9 MB, packed ~6.2/13.6/15.6 MB (~35 MB total). Updates arrive via the `data-batch` GitHub workflow (regular). GitHub hard-blocks files >100 MB — the DB is at 77% of that.

- [ ] **Step 2: Write the ADR**

Create `docs/decisions/0001-sqlite-git-lfs.md`:

```markdown
# ADR 0001: Store data/art-islands.sqlite in Git LFS

Date: <today>
Status: Accepted

## Context
- Current size: 76,910,592 bytes (~73 MiB) as of 2026-07-07.
- Growth: 13 MB → 32 MB → 77 MB across the three commits that touched it
  (init → db migration → some numbers). Expected to keep growing as new works
  and V2 domain tables are enriched.
- Update frequency: every approved data batch (`.github/workflows/data-batch.yml`
  opens a PR with a modified database), plus manual curation commits.
- Git impact so far: ~35 MB of pack data for 3 versions; each future update adds
  a full re-compressed blob (SQLite deltas poorly), i.e. ~15 MB+ per version at
  current size. Ten updates ≈ +150 MB of permanent history.
- GitHub rejects files over 100 MB outright; the DB is at ~77 % of the limit and
  a plain-Git workflow would eventually hard-fail a push.
- Git LFS free tier: 1 GB storage / 1 GB month bandwidth — enough for years of
  updates at this size; CI fetches only the current version.

## Decision
Track `data/*.sqlite` with Git LFS starting from the migration branch onward.
Do NOT rewrite existing history (explicitly out of scope per spec §9); the three
pre-LFS blobs stay in normal Git.

## Consequences
- Contributors need `git lfs install` once (documented in README).
- All GitHub Actions checkouts must pass `lfs: true` and CI validates it got a
  real SQLite file, not a pointer (`PRAGMA quick_check`).
- The SQLite file is never served through GitHub Pages; the app keeps loading
  the generated JSON exports only.
```

- [ ] **Step 3: Install git-lfs locally and start tracking**

```bash
brew install git-lfs
git lfs install
git lfs track "data/*.sqlite"
git add .gitattributes
git add --renormalize data/art-islands.sqlite
git status   # data/art-islands.sqlite should show as modified (now an LFS pointer in the index)
```
Expected `.gitattributes` content: `data/*.sqlite filter=lfs diff=lfs merge=lfs -text`.
Verify: `git lfs status` lists the sqlite; `git show :data/art-islands.sqlite | head -1` prints `version https://git-lfs.github.com/spec/v1`.
Also confirm `data/art-islands.sqlite-shm` / `-wal` remain ignored or uncommitted (they are untracked today; do not add them).

- [ ] **Step 4: Add `lfs: true` + validation to all three workflows**

In `.github/workflows/ci.yml`, `.github/workflows/pages.yml`, `.github/workflows/data-batch.yml` change every `- uses: actions/checkout@v4` to:

```yaml
      - uses: actions/checkout@v4
        with:
          lfs: true
```
(data-batch.yml already has `with: ref: main` — keep `ref` and add `lfs: true` under the same `with`.)

In `ci.yml`, insert a validation step BEFORE "Python tests":

```yaml
      - name: Validate LFS database is real SQLite
        run: |
          head -c 16 data/art-islands.sqlite | grep -q "SQLite format 3" \
            || { echo "data/art-islands.sqlite is an LFS pointer, not a database"; exit 1; }
          python - <<'PY'
          import sqlite3
          result = sqlite3.connect("data/art-islands.sqlite").execute("pragma quick_check").fetchone()[0]
          assert result == "ok", result
          print("quick_check ok")
          PY
```

- [ ] **Step 5: Document in README**

In `README.md` "Local installation", before `npm ci` add:

```markdown
This repository stores `data/art-islands.sqlite` in Git LFS. Install and enable
LFS once before cloning or pulling database updates:

```sh
brew install git-lfs   # or your platform's package manager
git lfs install
git lfs pull           # if you cloned before installing LFS
```
```

- [ ] **Step 6: Verify and commit**

```bash
git lfs ls-files        # expect: data/art-islands.sqlite
sqlite3 data/art-islands.sqlite "PRAGMA quick_check;"   # expect: ok
git add -A && git commit -m "feat: track SQLite database with Git LFS (ADR 0001)"
```

---

## Task 2: Close the Python V2 export gaps (FR-1, FR-9 data needs)

**Files:**
- Modify: `src/art_islands/v2.py`
- Modify: `src/art_islands/cli.py` (quick_check before exports)
- Test: `tests/test_v2.py`

**Interfaces:**
- Produces `public/data/v2/advisories.json` as `{"categories": [{"id","code","label"}], "advisories": [{"id","entityId","categoryId","severity","intensity","uncertainty","conceptId"}]}` (drops the ~53k repeated `description` strings — provenance boilerplate, not user-facing; saves ~4 MB).
- Produces `public/data/v2/ratings.json` as `{"systems": [{"id","code","countryCode","label"}], "ratings": [<unchanged rating rows>]}`.
- Produces `entities.json` WITHOUT the `texts` arrays (UI only ever uses `label`/`description`, which stay; saves ~40 % of 5.8 MB) — this is spec §5.10 "remove redundant payloads".
- Produces `export_v2_static_data` that raises `ValueError` if `pragma quick_check` fails.

- [ ] **Step 1: Write the failing tests** (extend `tests/test_v2.py`; reuse `create_domain_fixture`, extending it with an `advisory_categories` row + `entity_advisories` row + `age_rating_systems` row + `entity_age_ratings` row if the fixture lacks them — check the existing fixture first, it already creates the schema via `tools/clean_domain_database.SCHEMA`):

```python
def test_advisories_export_includes_categories(tmp_path):
    db_path = tmp_path / "domain.sqlite"
    create_domain_fixture(db_path)
    out = tmp_path / "out"
    v2.export_v2_static_data(db_path, out)
    payload = json.loads((out / "advisories.json").read_text())
    assert isinstance(payload, dict)
    assert {c["code"] for c in payload["categories"]} >= {"violence"}
    row = payload["advisories"][0]
    assert set(row) <= {"id", "entityId", "categoryId", "conceptId", "severity", "intensity", "uncertainty"}
    assert "description" not in row

def test_ratings_export_includes_systems(tmp_path):
    ...same pattern...
    payload = json.loads((out / "ratings.json").read_text())
    assert payload["systems"][0]["code"]
    assert payload["ratings"][0]["certificate"]

def test_entities_export_has_no_texts(tmp_path):
    ...
    entities = json.loads((out / "entities.json").read_text())
    assert all("texts" not in e for e in entities.values())
    assert any("description" in e for e in entities.values())

def test_export_fails_on_corrupt_database(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 4096)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        v2.export_v2_static_data(bad, tmp_path / "out")
```

- [ ] **Step 2: Run to verify they fail**: `.venv/bin/python -m pytest tests/test_v2.py -q` → new tests FAIL.

- [ ] **Step 3: Implement in `v2.py`**

At the top of `export_v2_static_data`, right after connecting:

```python
    check = db.execute("pragma quick_check").fetchone()[0]
    if check != "ok":
        raise ValueError(f"database failed quick_check: {check}")
```

Replace `export_v2_advisories` to return the dict shape (categories query: `select advisory_category_id as id, code, label from advisory_categories order by code`; advisory rows: same query as today minus `description`). Add `export_v2_age_rating_systems(db)` (`select age_rating_system_id as id, code, country_code as countryCode, label from age_rating_systems order by code`) and wrap ratings as `{"systems": systems, "ratings": rows}`. In `export_v2_entities`, delete the `texts` grouping and the `entity["texts"]` assignment.

Also apply the same quick_check guard in `model.export_static_data` (legacy export writes evolution.json; it must not run on a corrupt DB either).

- [ ] **Step 4: Run tests**: `.venv/bin/python -m pytest tests -q` → PASS (fix any existing tests asserting the old shapes).

- [ ] **Step 5: Regenerate real exports and eyeball sizes**

```bash
.venv/bin/art-islands db-v2 export
du -h public/data/v2/*.json    # advisories/entities should be visibly smaller
git add -A && git commit -m "feat: export advisory categories + rating systems, slim v2 payloads, validate db before export"
```

---

## Task 3: Settings schema v2 (spec §6) — TS + Python + data file

**Files:**
- Modify: `web/src/lib/types.ts` (Settings interfaces + `mergeSettings`)
- Modify: `src/art_islands/model.py` (`DEFAULT_SETTINGS`, `INT_SETTING_KEYS`, `settings_with_defaults`)
- Modify: `data/settings.json`
- Test: `web/src/lib/types.test.ts` (create), `tests/test_model.py`

**Interfaces (Produces — used by every later task):**

```ts
export interface FeatureSettings {
  directConceptMultiplier: number; creatorMultiplier: number; directorMultiplier: number;
  authorMultiplier: number; producerMultiplier: number; performerMultiplier: number;
  organizationMultiplier: number; contentGuideMultiplier: number;
}
export interface EvolutionSettings {
  visibleChildrenPerNode: number; maxInitialRoots: number; groupingSimilarity: number;
  minimumSimilarity: number; minimumSharedFeatures: number; kindMismatchFactor: number;
}
export interface IslandsSettings {
  maxRecommendationNodes: number; maxInferredNeighborsPerNode: number;
  maxEdges: number; minimumSimilarity: number;
}
export interface BrowseSettings { defaultPageSize: number; pageSizeOptions: number[]; }
export interface Settings {
  recommendation: RecommendationSettings; features: FeatureSettings;
  evolution: EvolutionSettings; islands: IslandsSettings; browse: BrowseSettings;
}
```

Legacy aliases accepted by BOTH languages when the new key is absent:
`islands.maxNeighborsPerSeed → islands.maxInferredNeighborsPerNode`, `evolution.minimumSharedTags → evolution.minimumSharedFeatures`.

Defaults (single source; spec §6 values): recommendation `{likeWeight:1.0, dislikeWeight:1.5, limit:100}`; features `{1.0, .55, .5, .55, .3, .25, .2, .25}` in the order above; evolution `{4, 20, 0.25, 0.18, 2, 0.6}`; islands `{150, 8, 500, 0.12}`; browse `{50, [25,50,100]}`.

- [ ] **Step 1: Failing TS tests** — create `web/src/lib/types.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, mergeSettings } from "./types";

describe("mergeSettings", () => {
  it("fills every section with defaults", () => {
    const s = mergeSettings({});
    expect(s.features.directorMultiplier).toBe(0.5);
    expect(s.browse.defaultPageSize).toBe(50);
    expect(s.browse.pageSizeOptions).toEqual([25, 50, 100]);
    expect(s.evolution.kindMismatchFactor).toBe(0.6);
  });
  it("migrates legacy setting names", () => {
    const s = mergeSettings({
      islands: { maxNeighborsPerSeed: 12 },
      evolution: { minimumSharedTags: 3 },
    });
    expect(s.islands.maxInferredNeighborsPerNode).toBe(12);
    expect(s.evolution.minimumSharedFeatures).toBe(3);
  });
  it("prefers the new name when both are present", () => {
    const s = mergeSettings({ islands: { maxNeighborsPerSeed: 12, maxInferredNeighborsPerNode: 6 } });
    expect(s.islands.maxInferredNeighborsPerNode).toBe(6);
  });
  it("rejects invalid values and non-numeric page sizes", () => {
    const s = mergeSettings({
      features: { directorMultiplier: -1 },
      browse: { defaultPageSize: 37, pageSizeOptions: ["a", 10] },
    });
    expect(s.features.directorMultiplier).toBe(0.5);
    expect(s.browse.pageSizeOptions).toEqual([25, 50, 100]); // invalid list → defaults
    expect(s.browse.defaultPageSize).toBe(50); // 37 not in options → default
  });
  it("keeps a valid custom page size that is in the options", () => {
    const s = mergeSettings({ browse: { defaultPageSize: 100 } });
    expect(s.browse.defaultPageSize).toBe(100);
  });
});
```

- [ ] **Step 2:** `npm run test:unit` → FAIL (missing keys).

- [ ] **Step 3: Implement `mergeSettings`** — rewrite in `types.ts`:

```ts
const LEGACY_ALIASES: Record<string, Record<string, string>> = {
  islands: { maxNeighborsPerSeed: "maxInferredNeighborsPerNode" },
  evolution: { minimumSharedTags: "minimumSharedFeatures" },
};

export function mergeSettings(raw: unknown): Settings {
  const source = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const merged = structuredClone(DEFAULT_SETTINGS) as unknown as Record<string, Record<string, unknown>>;
  for (const sectionName of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    const section = source[sectionName];
    if (!section || typeof section !== "object") continue;
    const incoming: Record<string, unknown> = { ...(section as Record<string, unknown>) };
    for (const [legacy, current] of Object.entries(LEGACY_ALIASES[sectionName] ?? {})) {
      if (incoming[current] === undefined && incoming[legacy] !== undefined) incoming[current] = incoming[legacy];
      delete incoming[legacy];
    }
    const target = merged[sectionName];
    for (const [name, value] of Object.entries(incoming)) {
      if (!(name in target)) continue;
      if (Array.isArray(target[name])) {
        const list = Array.isArray(value) ? value.map(Number).filter((n) => Number.isInteger(n) && n > 0) : [];
        if (list.length) target[name] = list;
      } else {
        const num = Number(value);
        if (Number.isFinite(num) && num >= 0) target[name] = num;
      }
    }
  }
  const result = merged as unknown as Settings;
  result.recommendation.limit = Math.max(1, Math.floor(result.recommendation.limit));
  if (!result.browse.pageSizeOptions.includes(result.browse.defaultPageSize)) {
    result.browse.defaultPageSize = DEFAULT_SETTINGS.browse.pageSizeOptions.includes(
      DEFAULT_SETTINGS.browse.defaultPageSize) ? DEFAULT_SETTINGS.browse.defaultPageSize : result.browse.pageSizeOptions[0];
  }
  return result;
}
```
Update `DEFAULT_SETTINGS` and the interfaces to the shapes above (keep `RecommendationSettings` as-is).

- [ ] **Step 4: Mirror in Python** — in `model.py`: extend `DEFAULT_SETTINGS` dict with `features` and `browse` sections and the renamed evolution/islands keys; add to `INT_SETTING_KEYS`: `minimumSharedFeatures`, `maxInferredNeighborsPerNode`, `defaultPageSize`, plus keep existing ones. In `settings_with_defaults`, before the per-key loop apply the same alias map, and special-case `pageSizeOptions` (list of positive ints, else default). Add tests in `tests/test_model.py`:

```python
def test_settings_defaults_include_new_sections():
    settings = settings_with_defaults({})
    assert settings["features"]["directorMultiplier"] == 0.5
    assert settings["browse"]["pageSizeOptions"] == [25, 50, 100]

def test_settings_legacy_aliases():
    settings = settings_with_defaults({"islands": {"maxNeighborsPerSeed": 12}})
    assert settings["islands"]["maxInferredNeighborsPerNode"] == 12
    assert "maxNeighborsPerSeed" not in settings["islands"]
```

- [ ] **Step 5: Update `data/settings.json`** to the full new shape (spec §6 JSON verbatim, i.e. islands.maxInferredNeighborsPerNode=8) and regenerate `public/data/settings.json` + `public/data/v2/settings.json` via `.venv/bin/art-islands export && .venv/bin/art-islands db-v2 export`.

- [ ] **Step 6: Run everything, fix compile fallout, commit** — `evolution.ts`, `islands.ts`, `recommendations.ts` reference renamed keys; update the references mechanically (`minimumSharedTags`→`minimumSharedFeatures`, `maxNeighborsPerSeed`→`maxInferredNeighborsPerNode`) so typecheck passes; their real rewrites come later.

```bash
npm run typecheck && npm run test:unit && .venv/bin/python -m pytest tests -q
git add -A && git commit -m "feat: settings schema v2 with features/browse sections and legacy aliases"
```

---

## Task 4: Normalized frontend domain layer (FR-1)

**Files:**
- Create: `web/src/lib/domain.ts`
- Modify: `web/src/lib/format.ts` (duration, scheme labels/URLs, advisory level, motion helper)
- Modify: `web/src/lib/types.ts` (V2 export shape updates from Task 2)
- Test: `web/src/lib/domain.test.ts`

**Interfaces:**
- Consumes: `V2Data` from `types.ts`. Update `V2Data` for Task 2's shapes:
  ```ts
  export interface V2AdvisoryCategory { id: number; code: string; label: string; }
  export interface V2Advisory { id: number; entityId: number; categoryId: number; conceptId?: number | null; severity?: string | null; intensity?: number | null; uncertainty?: number | null; }
  export interface V2AdvisoryExport { categories: V2AdvisoryCategory[]; advisories: V2Advisory[]; }
  export interface V2AgeRatingSystem { id: number; code: string; countryCode?: string | null; label: string; }
  export interface V2AgeRatingExport { systems: V2AgeRatingSystem[]; ratings: V2AgeRating[]; }
  // V2Data: advisories: V2AdvisoryExport; ratings: V2AgeRatingExport;
  // V2Entity: delete texts / V2EntityText.
  ```
- Produces (used by every later task):

```ts
export type BroadKind = "film" | "tv" | "music" | "game" | "work";
export interface NormalizedDate { type: string; value: string; precision: number; primary: boolean; }
export interface NormalizedConceptAssignment {
  conceptId: number; label: string; description?: string;
  category: string; categoryLabel: string; weight: number; polarity: number;
}
export interface NormalizedContributor {
  entityId: number; label: string; role: string; roleLabel: string;
  family: string; characterLabel?: string; weight: number; polarity: number;
}
export interface NormalizedMeasurement { type: string; number?: number; text?: string; unit?: string; qualifier?: string; }
export interface NormalizedDuration { seconds: number; label: string; }
export interface NormalizedAgeRating { system: string; certificate: string; minimumAge?: number; edition?: string; descriptors: string[]; }
export interface NormalizedAdvisory { categoryId: number; category: string; severity?: string; intensity?: number; uncertainty?: number; }
export interface NormalizedRestriction { type: string; countryCode?: string; region?: string; reason?: string; status?: string; startDate?: string; endDate?: string; edition?: string; }
export interface NormalizedIdentifier { scheme: string; label: string; value: string; url: string; primary: boolean; }

export interface WorkViewModel {
  id: number; label: string; description?: string;
  family: string; type: string; typeLabel: string; broadKind: BroadKind; image?: string;
  dates: NormalizedDate[]; primaryDate?: NormalizedDate; sortDate: string | null; year: number | null;
  concepts: NormalizedConceptAssignment[];
  conceptsByCategory: Record<string, NormalizedConceptAssignment[]>;
  contributors: NormalizedContributor[];
  contributorsByRole: Record<string, NormalizedContributor[]>;
  measurements: NormalizedMeasurement[]; duration?: NormalizedDuration;
  ageRatings: NormalizedAgeRating[]; advisories: NormalizedAdvisory[]; restrictions: NormalizedRestriction[];
  identifiers: NormalizedIdentifier[];
}
export interface DomainModel {
  works: WorkViewModel[];                  // catalog order (date asc as exported)
  workById: Map<number, WorkViewModel>;
  entityById: Map<number, V2Entity>;
  conceptById: Map<number, V2Concept>;
  conceptCategories: { code: string; label: string }[];
  typeOptions: { code: string; label: string; count: number }[];
  workRelations: V2Relation[];             // both endpoints are catalogued works
}
export function buildDomainModel(v2: V2Data): DomainModel;
export function roleLabel(code: string): string;
export function broadKindForType(code: string): BroadKind;
```

- [ ] **Step 1: format.ts additions (with failing tests first in `domain.test.ts`)**

```ts
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.round((total - hours * 3600) / 60);
  if (hours && minutes) return `${hours} h ${minutes} min`;
  if (hours) return `${hours} h`;
  return `${Math.max(1, minutes)} min`;
}
export function advisoryLevel(intensity?: number): "mild" | "moderate" | "high" | null {
  if (intensity === undefined || intensity === null) return null;
  return intensity >= 67 ? "high" : intensity >= 34 ? "moderate" : "mild";
}
export function motionDuration(ms: number): number {
  return typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : ms;
}
const SCHEME_INFO: Record<string, { label: string; url: (v: string) => string }> = {
  wikidata: { label: "Wikidata", url: (v) => `https://www.wikidata.org/wiki/${v}` },
  imdb_title: { label: "IMDb", url: (v) => `https://www.imdb.com/title/${v}/` },
  imdb_name: { label: "IMDb", url: (v) => `https://www.imdb.com/name/${v}/` },
  imdb_company: { label: "IMDb", url: (v) => `https://www.imdb.com/company/${v}/` },
  tmdb_movie: { label: "TMDB", url: (v) => `https://www.themoviedb.org/movie/${v}` },
  tmdb_tv: { label: "TMDB", url: (v) => `https://www.themoviedb.org/tv/${v}` },
  musicbrainz_release_group: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/release-group/${v}` },
  musicbrainz_artist: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/artist/${v}` },
  musicbrainz_recording: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/recording/${v}` },
  musicbrainz_work: { label: "MusicBrainz", url: (v) => `https://musicbrainz.org/work/${v}` },
  discogs_release: { label: "Discogs", url: (v) => `https://www.discogs.com/release/${v}` },
  discogs_master: { label: "Discogs", url: (v) => `https://www.discogs.com/master/${v}` },
  discogs_artist: { label: "Discogs", url: (v) => `https://www.discogs.com/artist/${v}` },
};
export function schemeLabel(scheme: string): string { return SCHEME_INFO[scheme]?.label ?? scheme.replace(/_/g, " "); }
export function identifierUrl(scheme: string, value: string): string { return SCHEME_INFO[scheme]?.url(value) ?? ""; }
```
Keep the legacy `KIND_LABELS`/`kindLabel`/`externalUrl` exports until Task 21 deletes them.

- [ ] **Step 2: Failing domain tests** — `web/src/lib/domain.test.ts`. Build a small `V2Data` literal fixture in the test file (two works, one person, one organization, concepts in two categories incl. one negative polarity, a duration measurement in seconds, one advisory, one age rating, one restriction, one adapted_from work→work relation, identifiers). Assert:

```ts
it("normalizes concepts grouped and sorted by weight then label", ...);
it("groups contributors by role with human role labels", ...);        // cast_member → "Cast"
it("derives duration from seconds and formats it", () => {
  expect(model.workById.get(1)!.duration).toEqual({ seconds: 8220, label: "2 h 17 min" });
});
it("keeps unknown concept categories under other", ...);
it("picks the primary date and falls back to compatibilityDate", ...);
it("maps primary entity type to broadKind", () => {
  expect(broadKindForType("film")).toBe("film");
  expect(broadKindForType("television_series")).toBe("tv");
  expect(broadKindForType("music_album")).toBe("music");
  expect(broadKindForType("video_game")).toBe("game");
  expect(broadKindForType("other_creative_work")).toBe("work");
});
it("collects work-to-work relations only", ...);                       // adapted_from kept, cast_member not
it("produces valid empty states when optional data is missing", () => {
  const bare = buildDomainModel(minimalV2());   // work with only id+label
  const work = bare.workById.get(9)!;
  expect(work.concepts).toEqual([]);
  expect(work.duration).toBeUndefined();
  expect(work.advisories).toEqual([]);
  expect(work.sortDate).toBeNull();
});
it("parses age rating descriptors from JSON and tolerates null", ...);
```

- [ ] **Step 3:** `npm run test:unit` → FAIL (module missing).

- [ ] **Step 4: Implement `domain.ts`.** Full implementation outline (write it exactly like this; ~230 lines):

```ts
const ROLE_LABELS: Record<string, string> = {
  director: "Director", creator: "Creator", author: "Author", screenwriter: "Screenwriter",
  cast_member: "Cast", voice_actor: "Voice cast", performer: "Performer",
  composer: "Composer", lyricist: "Lyricist", music_artist: "Artist",
  producer: "Producer", production_company: "Production company", record_label: "Record label",
  distributor: "Distributor", publisher: "Publisher", broadcaster: "Broadcaster",
  adapted_from: "Adapted from", influenced_by: "Influenced by", inspired_by: "Inspired by",
  influenced: "Influenced", main_subject: "Subject", depicts: "Depicts",
};
export function roleLabel(code: string): string {
  return ROLE_LABELS[code] ?? code.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
export function broadKindForType(code: string): BroadKind {
  if (code === "film") return "film";
  if (code === "television_series") return "tv";
  if (code === "music_album" || code === "musical_work") return "music";
  if (code === "video_game") return "game";
  return "work";
}
```
`buildDomainModel(v2)`:
1. `entityById` = new Map over `Object.values(v2.entities)` keyed by `entity.id`. `conceptById` from `v2.concepts.concepts`. `categoryLabels` from `v2.concepts.categories` (code→label).
2. `typeById` from `v2.entityTypes.definitions`; `primaryType` = first assignment per entity with `isPrimary===1` (assignments are pre-sorted by entityId,typeId).
3. Group by entityId: `v2.concepts.entityConcepts`, `v2.relations` (by `source`), `v2.advisories.advisories`, `v2.ratings.ratings`, `v2.restrictions`. `systems` map from `v2.ratings.systems`.
4. For each `V2CatalogItem`: build WorkViewModel —
   - dates: normalize each `V2Date` (`primary: Boolean(d.primary)`); `primaryDate = dates.find(d => d.primary) ?? dates[0]`; if none and `compatibilityDate` present, synthesize `{type:"compatibility", value: item.compatibilityDate, precision: item.compatibilityDatePrecision ?? 3, primary:true}`; `sortDate = primaryDate?.value ?? null`; `year = sortDate ? Number(sortDate.slice(0,4)) : null` (guard NaN → null).
   - concepts: map entityConcepts → NormalizedConceptAssignment via `conceptById` (skip missing ids), `categoryLabel = categoryLabels.get(category) ?? "Other"`; sort weight desc, label asc, conceptId asc; group into `conceptsByCategory` (unknown category code → key `"other"`).
   - contributors: relations from this work → target entity via `entityById` (`label` fallback `` `Entity ${id}` ``, family fallback `"unknown"`); `role = relation.type`; sort by role asc, weight desc, label asc; group `contributorsByRole`.
   - measurements: copy fields; `duration`: first measurement `type==="duration"` with a number → seconds = `unit==="minutes" ? n*60 : unit==="hours" ? n*3600 : n`; label via `formatDuration`.
   - ageRatings: `{ system: systems.get(systemId)?.label ?? "Rating", certificate, minimumAge, edition, descriptors: safeParse(descriptorsJson) }` where safeParse returns `string[]` or `[]`.
   - advisories: `{ categoryId, category: advisoryCategoryLabels.get(categoryId) ?? "Content", severity, intensity, uncertainty }`, sorted intensity desc then category asc.
   - restrictions: copy/rename fields.
   - identifiers: from `entityById.get(id)?.identifiers` → `{scheme, label: schemeLabel(scheme), value, url: identifierUrl(scheme, value), primary}`; sort primary desc, label asc; de-duplicate identical scheme+value.
   - description from `entityById.get(id)?.description`; type/typeLabel/broadKind from `primaryType` (fallback `{code:"other_creative_work", label:"Work"}`).
5. `typeOptions`: count works per type code, sorted by label. `workRelations`: `v2.relations.filter(r => catalogIds.has(r.source) && catalogIds.has(r.target))`.

- [ ] **Step 5:** `npm run test:unit` → PASS. `npm run typecheck` → PASS.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: normalized V2 frontend domain layer"`

---

## Task 5: TypeScript feature model (FR-7, FR-8, §4)

**Files:**
- Create: `web/src/lib/features.ts`
- Create: `docs/feature-model.md`
- Test: `web/src/lib/features.test.ts`

**Interfaces:**
- Consumes: `WorkViewModel`, `DomainModel` (Task 4); `FeatureSettings` (Task 3).
- Produces:

```ts
export type FeatureSource = "direct-concept" | "contributor" | "organization" | "content-guide";
export interface WeightedFeature {
  key: string; label: string; value: number; source: FeatureSource;
  category?: string;                       // concept category label, for phrasing
  sourceEntityId?: number; relationType?: string;
}
export interface EdgeFactor {
  id: string; label: string; contribution: number; source: FeatureSource;
  category?: string; relationType?: string;
}
export interface FeatureSimilarity { similarity: number; sharedFeatureCount: number; topFactors: EdgeFactor[]; }
export interface FeatureIndex {
  featuresById: Map<number, WeightedFeature[]>;   // FINAL values (IDF applied)
  vectors: Map<number, Map<string, number>>;
  norms: Map<number, number>;
  idf: Map<string, number>;
  documentFrequency: Map<string, number>;
  postings: Map<string, number[]>;
  size: number;
}
export const CANDIDATE_FEATURE_DF_CAP = 150;
export function extractWorkFeatures(work: WorkViewModel, settings: FeatureSettings): WeightedFeature[];
export function buildFeatureIndex(works: WorkViewModel[], settings: FeatureSettings): FeatureIndex;
export function similarityBetween(index: FeatureIndex, aId: number, bId: number, topCount?: number): FeatureSimilarity;
export function similarityCandidates(index: FeatureIndex, entityId: number, allowed?: Set<number>): Set<number>;
export function factorPhrase(factor: { source: FeatureSource; label: string; category?: string; relationType?: string }): string;
```

- [ ] **Step 1: Write `docs/feature-model.md`** — the single documented semantics both languages implement:

```markdown
# Canonical feature and similarity semantics

One specification for Python (build-time Evolution) and TypeScript
(Browse relevance, Recommendations, Islands). Golden fixtures in
`shared/fixtures/feature-golden.json` verify both implementations agree.

## Feature keys
- `concept:<conceptId>` — direct work concept. source `direct-concept`.
- `entity:<entityId>`  — one-hop contributor/organization inheritance.
  source `contributor`, or `organization` when the target entity family is
  organization/group. No propagation beyond one hop, ever.
- `advisory:<categoryId>` — content-guide (advisory) profile. source `content-guide`.

## Values
magnitude  = clamp(weight / 100, 0, 1)          (advisories use intensity)
sign       = -1 if polarity < 0 else +1         (advisories always +1)
base       = magnitude × sign × sourceMultiplier
final      = base × idf(key)
idf(key)   = ln(1 + N / df(key)) over all catalogued works

Source multipliers come from settings.features. Role → multiplier map
(roles not listed contribute NO inherited feature):
creator, composer, lyricist, music_artist        → creatorMultiplier
director                                          → directorMultiplier
author, screenwriter                              → authorMultiplier
producer                                          → producerMultiplier
cast_member, voice_actor, performer               → performerMultiplier
production_company, record_label, distributor,
publisher, broadcaster                            → organizationMultiplier
Direct concepts                                   → directConceptMultiplier
Advisories                                        → contentGuideMultiplier
When the same target entity appears through several roles, keep the single
feature with the largest |value| (ties: first role in ascending role-code
order). This is the per-source cap that stops high-degree entities from
stacking.

## Similarity
cosine(a, b) = Σ_k a[k]·b[k] / (‖a‖·‖b‖) over final values.
Opposite signs subtract (opposite polarity reduces compatibility).
sharedFeatureCount = number of keys present in both vectors.
A similarity ≤ 0 never creates an inferred edge.
topFactors = shared keys sorted by contribution desc (ties: key asc), top 3.

## Candidate generation
Inverted index key → work ids. Keys with df > 150 are scored but never used
for candidate generation (bounded fan-out, no all-pairs loops).

## Determinism
All sorts specify total orders (value/contribution desc, then key/id asc).
```

- [ ] **Step 2: Failing tests** — `web/src/lib/features.test.ts`. Build works via a tiny helper `work(id, overrides): WorkViewModel` that fills empty defaults. Test cases (these implement spec §FR-7 acceptance directly):

```ts
it("higher weight on a matching feature raises similarity", ...);   // two pairs, one with weight 90 vs 40
it("opposite polarity decreases compatibility", () => {
  // A and B share concept X positively; A and C share X with polarity -1 on C
  expect(sim(a, c).similarity).toBeLessThan(sim(a, b).similarity);
});
it("negative shared evidence can make similarity non-positive", ...);
it("generic concepts contribute less than rare ones (IDF)", ...);   // concept on all 6 works vs on 2
it("contributor features use role multipliers and are weaker than direct concepts", () => {
  const features = extractWorkFeatures(w, settings);
  const direct = features.find((f) => f.key === "concept:1")!;
  const director = features.find((f) => f.key === "entity:50")!;
  expect(Math.abs(director.value)).toBeLessThan(Math.abs(direct.value));
  expect(director.source).toBe("contributor");
  expect(director.relationType).toBe("director");
});
it("keeps only the strongest role for a repeated entity", ...);      // same person as director+producer → one entity:<id> feature, director multiplier
it("unmapped roles (main_subject) produce no inherited feature", ...);
it("organization targets get source organization", ...);
it("advisories become content-guide features from intensity", ...);
it("candidate generation is bounded by the DF cap and allowed set", ...);
it("similarityBetween reports sharedFeatureCount and labeled topFactors", ...);
it("deterministic: same input twice gives deeply equal results", ...);
```

- [ ] **Step 3:** `npm run test:unit` → FAIL.

- [ ] **Step 4: Implement `features.ts`** (complete):

```ts
import type { WorkViewModel } from "./domain";
import type { FeatureSettings } from "./types";

export const CANDIDATE_FEATURE_DF_CAP = 150;

const ROLE_MULTIPLIER_KEY: Record<string, keyof FeatureSettings> = {
  creator: "creatorMultiplier", composer: "creatorMultiplier",
  lyricist: "creatorMultiplier", music_artist: "creatorMultiplier",
  director: "directorMultiplier",
  author: "authorMultiplier", screenwriter: "authorMultiplier",
  producer: "producerMultiplier",
  cast_member: "performerMultiplier", voice_actor: "performerMultiplier", performer: "performerMultiplier",
  production_company: "organizationMultiplier", record_label: "organizationMultiplier",
  distributor: "organizationMultiplier", publisher: "organizationMultiplier", broadcaster: "organizationMultiplier",
};

function magnitude(weight: number): number { return Math.max(0, Math.min(1, weight / 100)); }
function polaritySign(polarity: number): 1 | -1 { return polarity < 0 ? -1 : 1; }

export function extractWorkFeatures(work: WorkViewModel, settings: FeatureSettings): WeightedFeature[] {
  const byKey = new Map<string, WeightedFeature>();
  for (const concept of work.concepts) {
    const value = magnitude(concept.weight) * polaritySign(concept.polarity) * settings.directConceptMultiplier;
    if (value === 0) continue;
    byKey.set(`concept:${concept.conceptId}`, {
      key: `concept:${concept.conceptId}`, label: concept.label, value,
      source: "direct-concept", category: concept.categoryLabel,
    });
  }
  for (const contributor of work.contributors) {   // already sorted by role asc
    const multiplierKey = ROLE_MULTIPLIER_KEY[contributor.role];
    if (!multiplierKey) continue;
    const value = magnitude(contributor.weight) * polaritySign(contributor.polarity) * settings[multiplierKey];
    if (value === 0) continue;
    const key = `entity:${contributor.entityId}`;
    const existing = byKey.get(key);
    if (existing && Math.abs(existing.value) >= Math.abs(value)) continue;
    byKey.set(key, {
      key, label: contributor.label, value,
      source: contributor.family === "organization" || contributor.family === "group" ? "organization" : "contributor",
      sourceEntityId: contributor.entityId, relationType: contributor.role,
    });
  }
  for (const advisory of work.advisories) {
    if (advisory.intensity === undefined || advisory.intensity === null) continue;
    const value = magnitude(advisory.intensity) * settings.contentGuideMultiplier;
    if (value === 0) continue;
    byKey.set(`advisory:${advisory.categoryId}`, {
      key: `advisory:${advisory.categoryId}`, label: advisory.category, value, source: "content-guide",
    });
  }
  return [...byKey.values()].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

export function buildFeatureIndex(works: WorkViewModel[], settings: FeatureSettings): FeatureIndex {
  const baseById = new Map<number, WeightedFeature[]>();
  const documentFrequency = new Map<string, number>();
  for (const work of works) {
    const features = extractWorkFeatures(work, settings);
    baseById.set(work.id, features);
    for (const feature of features) {
      documentFrequency.set(feature.key, (documentFrequency.get(feature.key) || 0) + 1);
    }
  }
  const total = Math.max(1, works.length);
  const idf = new Map<string, number>();
  for (const [key, df] of documentFrequency) idf.set(key, Math.log(1 + total / df));

  const featuresById = new Map<number, WeightedFeature[]>();
  const vectors = new Map<number, Map<string, number>>();
  const norms = new Map<number, number>();
  const postings = new Map<string, number[]>();
  for (const work of works) {
    const finals: WeightedFeature[] = [];
    const vector = new Map<string, number>();
    let squared = 0;
    for (const feature of baseById.get(work.id) || []) {
      const value = feature.value * (idf.get(feature.key) || 0);
      if (value === 0) continue;
      finals.push({ ...feature, value });
      vector.set(feature.key, value);
      squared += value * value;
      let list = postings.get(feature.key);
      if (!list) postings.set(feature.key, (list = []));
      list.push(work.id);
    }
    featuresById.set(work.id, finals);
    vectors.set(work.id, vector);
    norms.set(work.id, Math.sqrt(squared));
  }
  return { featuresById, vectors, norms, idf, documentFrequency, postings, size: works.length };
}

export function similarityBetween(index: FeatureIndex, aId: number, bId: number, topCount = 3): FeatureSimilarity {
  const a = index.vectors.get(aId);
  const b = index.vectors.get(bId);
  const normA = index.norms.get(aId) || 0;
  const normB = index.norms.get(bId) || 0;
  if (!a || !b || normA === 0 || normB === 0) return { similarity: 0, sharedFeatureCount: 0, topFactors: [] };
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  let dot = 0;
  const shared: { key: string; contribution: number }[] = [];
  for (const [key, value] of small) {
    const other = large.get(key);
    if (other === undefined) continue;
    const contribution = value * other;
    dot += contribution;
    shared.push({ key, contribution });
  }
  shared.sort((x, y) => y.contribution - x.contribution || (x.key < y.key ? -1 : 1));
  const meta = new Map((index.featuresById.get(aId) || []).map((f) => [f.key, f]));
  const topFactors: EdgeFactor[] = shared.slice(0, topCount).map(({ key, contribution }) => {
    const feature = meta.get(key);
    return {
      id: key, label: feature?.label ?? key, contribution,
      source: feature?.source ?? "direct-concept",
      category: feature?.category, relationType: feature?.relationType,
    };
  });
  return { similarity: dot / (normA * normB), sharedFeatureCount: shared.length, topFactors };
}

export function similarityCandidates(index: FeatureIndex, entityId: number, allowed?: Set<number>): Set<number> {
  const candidates = new Set<number>();
  const vector = index.vectors.get(entityId);
  if (!vector) return candidates;
  for (const key of vector.keys()) {
    if ((index.documentFrequency.get(key) || 0) > CANDIDATE_FEATURE_DF_CAP) continue;
    for (const otherId of index.postings.get(key) || []) {
      if (otherId === entityId) continue;
      if (allowed && !allowed.has(otherId)) continue;
      candidates.add(otherId);
    }
  }
  return candidates;
}

export function factorPhrase(factor: { source: FeatureSource; label: string; category?: string; relationType?: string }): string {
  if (factor.source === "direct-concept") {
    return `Shared ${factor.category ? factor.category.toLowerCase() : "concept"}: ${factor.label}`;
  }
  if (factor.source === "content-guide") return `Similar content advisory: ${factor.label}`;
  if (factor.source === "organization") return `Shared ${roleName(factor.relationType)}: ${factor.label}`;
  return `Same ${roleName(factor.relationType)}: ${factor.label}`;
}
function roleName(role?: string): string { return role ? role.replace(/_/g, " ") : "contributor"; }
```
(Import `WeightedFeature`, `EdgeFactor`, `FeatureSimilarity`, `FeatureIndex`, `FeatureSource` types declared in this same file.)

- [ ] **Step 5:** `npm run test:unit` → PASS; `npm run typecheck` → PASS.

- [ ] **Step 6: Commit** — `git commit -am "feat: shared weighted polarity-aware feature model (TypeScript)"`

---

## Task 6: Python feature model + shared golden fixtures (FR-7 cross-language)

**Files:**
- Create: `src/art_islands/features.py`
- Create: `tools/generate_feature_golden.py`
- Create: `shared/fixtures/feature-golden.json` (generated)
- Test: `tests/test_features.py`, `web/src/lib/features.golden.test.ts`

**Interfaces:**
- Consumes: `docs/feature-model.md` semantics; settings dict (`features` section).
- Produces (used by Task 11's evolution rewrite):

```python
# src/art_islands/features.py
ROLE_MULTIPLIER_KEYS: dict[str, str]          # same map as TS
CANDIDATE_FEATURE_DF_CAP = 150

@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    value: float          # base value (pre-IDF)
    source: str           # direct-concept | contributor | organization | content-guide
    category: str | None = None
    relation_type: str | None = None

def extract_features(concepts, contributors, advisories, feature_settings) -> dict[str, Feature]
#   concepts:     [(concept_id, label, category_label, weight, polarity)]
#   contributors: [(entity_id, label, family, role, weight, polarity)]  (sorted role asc)
#   advisories:   [(category_id, label, intensity)]
@dataclass
class FeatureIndex:
    features_by_id: dict[int, dict[str, Feature]]   # final values
    vectors: dict[int, dict[str, float]]
    norms: dict[int, float]
    idf: dict[str, float]
    document_frequency: dict[str, int]
    postings: dict[str, list[int]]

def build_feature_index(base_features: dict[int, dict[str, Feature]]) -> FeatureIndex
def similarity_between(index, a_id, b_id, top_count=3) -> tuple[float, int, list[dict]]
#   list entries: {"id","label","contribution","source"} (+category/relationType when set)
```

- [ ] **Step 1: Failing Python tests** — `tests/test_features.py`, mirroring the TS test cases (weight raises similarity; opposite polarity decreases; IDF downweights generic; role multipliers; strongest-role dedupe; unmapped roles skipped; determinism). Use plain tuples per the interface above, no DB.

- [ ] **Step 2:** `pytest tests/test_features.py -q` → FAIL.

- [ ] **Step 3: Implement `features.py`** as a line-for-line semantic port of Task 5's `features.ts` (magnitude/sign helpers, dedupe by max |value| with first-wins tie on sorted roles, `math.log(1 + total/df)`, dot over the smaller dict, tie-break contribution desc then key asc). Keep float math in the same operation ORDER as TS so results agree bit-for-bit in practice (both are IEEE-754 doubles).

- [ ] **Step 4:** `pytest tests/test_features.py -q` → PASS.

- [ ] **Step 5: Golden fixture generator** — `tools/generate_feature_golden.py`:

```python
"""Regenerate shared/fixtures/feature-golden.json from the Python reference
implementation. TypeScript must reproduce these numbers within 1e-9."""
```
Define FIXTURE inline: settings = spec §6 features defaults; 8 abstract works covering: positive/negative polarity, weights 30/60/90, one concept present on ALL works (generic) vs pair-only concepts (rare), a shared director, conflicting contributor evidence (same entity positive on one work / polarity -1 on another), shared advisory category with different intensities, cross-family works (film vs music_album), one undated work. Compute per work: base features + final features; compute the full pairwise similarity list `[{a, b, similarity, sharedFeatureCount, topFactors}]` for a,b in ascending id pairs. Write JSON:

```json
{
  "settings": { ...features section... },
  "works": [{"id":1,"date":"1980-01-01","kind":"film",
             "concepts":[{"id":10,"label":"Cyberpunk","category":"Genre","weight":90,"polarity":0}],
             "contributors":[{"entityId":50,"label":"R. Scott","family":"person","role":"director","weight":80,"polarity":0}],
             "advisories":[{"categoryId":1,"label":"Violence","intensity":72}]}, ...],
  "expected": {
    "features": {"1": {"concept:10": 1.234..., "entity:50": ...}, ...},
    "similarities": [{"a":1,"b":2,"similarity":0.64...,"sharedFeatureCount":3,
                      "topFactors":[{"id":"concept:10","label":"Cyberpunk","contribution":0.31,"source":"direct-concept"}]}]
  }
}
```
Run `python tools/generate_feature_golden.py` to write the file.

- [ ] **Step 6: Lock both sides to the golden file**
  - `tests/test_features.py::test_golden_fixture_is_current` — regenerate in-memory and `assert regenerated == json.loads(path.read_text())` (drift guard, tells the developer to rerun the generator intentionally).
  - `web/src/lib/features.golden.test.ts` — read the JSON with `readFileSync(new URL("../../../shared/fixtures/feature-golden.json", import.meta.url))` (vitest runs in node env), convert each fixture work into a minimal `WorkViewModel` (helper in the test), run `buildFeatureIndex` + `similarityBetween`, and assert every expected feature value and similarity with `toBeCloseTo(expected, 9)` and exact `sharedFeatureCount` / `topFactors` ids and sources.

- [ ] **Step 7:** `pytest tests -q && npm run test:unit` → PASS.

- [ ] **Step 8: Commit** — `git commit -am "feat: Python feature model + cross-language golden fixtures"`

---

## Task 7: V2 becomes the required canonical data source (FR-1)

**Files:**
- Modify: `web/src/lib/data.ts`, `web/src/lib/types.ts` (`AppData`)
- Test: `web/src/lib/data.test.ts` (create; pure validation functions only)

**Interfaces:**
- Produces:

```ts
// types.ts
export interface AppData {
  v2: V2Data;
  domain: DomainModel;
  evolution: EvolutionExport | null;   // optional: view shows regeneration hint
}
// data.ts
export function validateV2Data(parts: Record<string, unknown>): { data: V2Data } | { missing: string[]; invalid: string[] };
export async function loadAppData(): Promise<{ data: AppData; settings: Settings }>;
```

- [ ] **Step 1: Failing tests** for `validateV2Data`: required parts = `catalog` (array), `entities` (object), `entityTypes` ({definitions,assignments} arrays), `relations` (array), `concepts` ({categories,concepts,entityConcepts} arrays). Optional-with-empty-default: `advisories` → `{categories:[],advisories:[]}`, `ratings` → `{systems:[],ratings:[]}`, `restrictions` → `[]`. Tests: all-present passes; missing catalog → `missing:["v2/catalog.json"]`; concepts as an array (wrong shape) → `invalid:["v2/concepts.json"]`; absent advisories → passes with empty default.

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: Implement.** `loadAppData` fetches ONLY: the eight `v2/*.json` files + `evolution.json` (optional) + `settings.json`. Delete the `catalog.json`/`tags.json`/`entities-lookup.json` fetches (FR-1 rule 3 + §5.10: the legacy payload is no longer downloaded). On validation failure throw:

```ts
throw new Error(
  `The V2 data exports are missing or invalid (${problems.join(", ")}). ` +
  `Regenerate them with: .venv/bin/art-islands export && .venv/bin/art-islands db-v2 export`,
);
```
Build `domain: buildDomainModel(v2)` here so every consumer gets memoized normalized models (§5.4). Evolution: `loadOptionalJson<EvolutionExport>("evolution.json")`, and treat `version !== 2` as `null` (Task 11 bumps the version; a stale file must show the regeneration hint, not crash).

- [ ] **Step 4:** typecheck will now break `App.tsx` and views (AppData shape changed). Add MINIMAL mechanical shims so the app still compiles and runs on legacy-free data: in `App.tsx` replace `data.catalog`/`tagIndex` usage with `data.domain.works` + `buildFeatureIndex` (details in Task 13 — if doing tasks in order, do the small App/View edits now only as far as needed to compile; Task 13-18 finish them). Run `npm run typecheck && npm run test:unit`.

- [ ] **Step 5: Commit** — `git commit -am "feat: V2 exports are the canonical frontend data source"`

---

## Task 8: Recommendations on the feature model (FR-7, FR-8)

**Files:**
- Modify: `web/src/lib/recommendations.ts` (full rewrite)
- Test: `web/src/lib/recommendations.test.ts` (rewrite)

**Interfaces:**
- Consumes: `FeatureIndex`, `EdgeFactor`, `factorPhrase` (Task 5); `DomainModel` (Task 4); `Ratings`, `Settings` (types.ts).
- Produces:

```ts
export interface ScoreContribution extends EdgeFactor {}   // contribution = signed score amount
export interface ScoredRecommendation {
  work: WorkViewModel; score: number;
  positive: ScoreContribution[];   // sorted desc, all kept (UI slices)
  negative: ScoreContribution[];   // sorted by |contribution| desc
}
export function scoreRecommendations(domain: DomainModel, index: FeatureIndex, ratings: Ratings, settings: Settings): ScoredRecommendation[];
export function explanationText(result: ScoredRecommendation, topCount?: number): string;
```

- [ ] **Step 1: Failing tests** (rewrite the file; build 6 works via the Task 5 test helper + `buildFeatureIndex`):

```ts
it("returns empty without likes", ...);
it("excludes already rated works", ...);
it("requires positive evidence", ...);                      // work sharing only disliked features → absent
it("disliked evidence subtracts", ...);                     // same candidate scores lower once a shared-feature work is disliked
it("candidate weight and polarity matter", ...);            // higher-weight match outranks lower; negative-polarity match does not count as positive
it("inherited contributor evidence is weaker than direct", ...);
it("keeps positive and negative contributions for explanation", () => {
  const [top] = scoreRecommendations(domain, index, { "1": 1, "2": -1 }, settings);
  expect(top.positive[0].label).toBeTruthy();
  expect(top.negative.length).toBeGreaterThan(0);
  expect(explanationText(top)).toMatch(/Shared|Same/);
});
it("is deterministic and respects the limit", ...);
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: Implement** (complete):

```ts
export function scoreRecommendations(domain, index, ratings, settings): ScoredRecommendation[] {
  const config = settings.recommendation;
  const profile = new Map<string, number>();
  let likedCount = 0;
  for (const work of domain.works) {
    const rating = ratings[String(work.id)];
    if (rating !== 1 && rating !== -1) continue;
    const direction = rating === 1 ? config.likeWeight : -config.dislikeWeight;
    if (rating === 1) likedCount += 1;
    for (const [key, value] of index.vectors.get(work.id) || []) {
      profile.set(key, (profile.get(key) || 0) + direction * value);
    }
  }
  if (!likedCount) return [];

  const scored: ScoredRecommendation[] = [];
  for (const work of domain.works) {
    const rating = ratings[String(work.id)];
    if (rating === 1 || rating === -1) continue;
    const vector = index.vectors.get(work.id);
    if (!vector || vector.size === 0) continue;
    const meta = new Map((index.featuresById.get(work.id) || []).map((f) => [f.key, f]));
    let score = 0;
    const positive: ScoreContribution[] = [];
    const negative: ScoreContribution[] = [];
    for (const [key, value] of vector) {
      const evidence = profile.get(key);
      if (evidence === undefined) continue;
      const amount = value * evidence;
      if (amount === 0) continue;
      score += amount;
      const feature = meta.get(key)!;
      const entry: ScoreContribution = {
        id: key, label: feature.label, contribution: amount,
        source: feature.source, category: feature.category, relationType: feature.relationType,
      };
      (amount > 0 ? positive : negative).push(entry);
    }
    if (!positive.length) continue;
    score /= Math.pow(Math.max(1, vector.size), 0.35);
    if (score <= 0) continue;
    positive.sort((a, b) => b.contribution - a.contribution || (a.id < b.id ? -1 : 1));
    negative.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution) || (a.id < b.id ? -1 : 1));
    scored.push({ work, score, positive, negative });
  }
  return scored
    .sort((a, b) =>
      b.score - a.score ||
      (a.work.sortDate || "9999-99-99").localeCompare(b.work.sortDate || "9999-99-99") ||
      a.work.label.localeCompare(b.work.label) || a.work.id - b.work.id)
    .slice(0, config.limit);
}

export function explanationText(result: ScoredRecommendation, topCount = 3): string {
  const parts = result.positive.slice(0, topCount).map(factorPhrase);
  if (result.negative.length) parts.push(`offset by: ${factorPhrase(result.negative[0])}`);
  return parts.join(" · ");
}
```
Delete the old `normalizedTagMap`/`explanation` exports (grep for usages: `islands.ts`, `RecommendationsView.tsx` — updated in Tasks 10/16).

- [ ] **Step 4:** `npm run test:unit` → PASS (islands tests may break; if so update imports minimally or proceed to Task 10 in the same session before committing). `npm run typecheck`.

- [ ] **Step 5: Commit** — `git commit -am "feat: feature-based recommendation scoring with explainable contributions"`

---

## Task 9: Pagination helpers (FR-3 logic)

**Files:**
- Create: `web/src/lib/pagination.ts`
- Test: `web/src/lib/pagination.test.ts`

**Interfaces:** Produces (consumed by Tasks 13/14):

```ts
export interface PageResult<T> { pageItems: T[]; page: number; pageCount: number; totalItems: number; }
export function clampPage(page: number, totalItems: number, pageSize: number): number;
export function paginate<T>(items: T[], page: number, pageSize: number): PageResult<T>;
```

- [ ] **Step 1: Failing tests**

```ts
it("slices the requested page", () => {
  const r = paginate([...Array(120).keys()], 2, 50);
  expect(r.pageItems[0]).toBe(50);
  expect(r.pageItems).toHaveLength(50);
  expect(r.pageCount).toBe(3);
  expect(r.totalItems).toBe(120);
});
it("clamps overflowing pages when results shrink", () => {
  expect(clampPage(9, 120, 50)).toBe(3);
  expect(paginate([...Array(10).keys()], 9, 50).page).toBe(1);
});
it("handles empty lists as a single empty page", () => {
  const r = paginate([], 1, 50);
  expect(r).toEqual({ pageItems: [], page: 1, pageCount: 1, totalItems: 0 });
});
it("normalizes nonsense input", () => {
  expect(clampPage(0, 100, 50)).toBe(1);
  expect(clampPage(NaN, 100, 50)).toBe(1);
});
```

- [ ] **Step 2:** FAIL → **Step 3: Implement**

```ts
export function clampPage(page: number, totalItems: number, pageSize: number): number {
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const pageCount = Math.max(1, Math.ceil(totalItems / size));
  const wanted = Math.floor(page) || 1;
  return Math.min(Math.max(1, wanted), pageCount);
}
export function paginate<T>(items: T[], page: number, pageSize: number): PageResult<T> {
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const totalItems = items.length;
  const pageCount = Math.max(1, Math.ceil(totalItems / size));
  const current = clampPage(page, totalItems, size);
  return { pageItems: items.slice((current - 1) * size, current * size), page: current, pageCount, totalItems };
}
```

- [ ] **Step 4:** PASS → **Step 5: Commit** `git commit -am "feat: pagination helpers"`

---

## Task 10: Islands on the feature model (FR-4)

**Files:**
- Modify: `web/src/lib/islands.ts`
- Test: `web/src/lib/islands.test.ts`

**Interfaces:**
- Consumes: `DomainModel.workRelations`, `FeatureIndex`, `similarityBetween`, `similarityCandidates` (Tasks 4/5), `scoreRecommendations` (Task 8), `IslandsSettings.maxInferredNeighborsPerNode` (Task 3).
- Produces:

```ts
export interface IslandNode {
  id: number; state: "liked" | "disliked" | "recommended";
  score?: number; topFactors?: EdgeFactor[];        // recommendation evidence for tooltips
}
export interface IslandEdge {
  source: number; target: number;                    // source < target, undirected
  kind: "similarity" | "explicit";
  similarity: number; sharedFeatureCount: number; topFactors: EdgeFactor[];
  relationType?: string;                             // e.g. "adapted_from" for explicit edges
}
export interface IslandsGraph { nodes: IslandNode[]; edges: IslandEdge[]; components: IslandComponent[]; }
export function buildIslandsGraph(domain: DomainModel, index: FeatureIndex, ratings: Ratings, settings: Settings): IslandsGraph;
// connectedComponents(nodes, edges) — keep exactly as-is
```

- [ ] **Step 1: Update tests.** Keep the existing structural tests (component determinism, explicit-edge preservation, edge cap, disconnected components) but port fixtures from `CatalogItem.tags` to domain works + feature index. ADD the FR-4 acceptance tests:

```ts
it("each node selects at most K inferred neighbors (union may exceed K incident)", () => {
  // star fixture: node 1 similar to 12 others, K=3 → node 1 contributes 3 selections;
  // count selections, not incident edges
});
it("no inferred edge from non-positive similarity", ...);   // opposite-polarity pair with negative cosine → no edge
it("explicit relations survive even when outside the K nearest", ...);
it("explicit edges carry their relation type and stay distinguishable", () => {
  expect(edge.kind).toBe("explicit");
  expect(edge.relationType).toBe("adapted_from");
});
it("global maxEdges cap applies with explicit edges first", ...);
it("deterministic edge ordering", ...);
```

- [ ] **Step 2:** FAIL → **Step 3: Implement.** The current file's structure survives; the changes:
  1. Signature: `buildIslandsGraph(domain, index, ratings, settings)`; `config.maxInferredNeighborsPerNode` replaces `maxNeighborsPerSeed`.
  2. Nodes: liked/disliked from `domain.works` ratings; recommended from Task 8 `scoreRecommendations` limited to `maxRecommendationNodes`, storing `score` and `topFactors: rec.positive.slice(0, 3)`.
  3. Inferred edges: for each displayed node, `similarityCandidates(index, node.id, displayed)` → `similarityBetween` → require `result.similarity >= config.minimumSimilarity && result.similarity > 0` → sort by similarity desc, source asc, target asc → take `maxInferredNeighborsPerNode` → union dedupe by `edgeKey` (identical to today).
  4. Explicit edges: replace the `item.links` loop with `domain.workRelations` — for each relation with both endpoints displayed, add edge `{kind:"explicit", relationType: relation.type, ...similarityBetween(...)}` deduped per pair (first by relation id order).
  5. Cap and components: unchanged (explicit sorted first, then inferred, `maxEdges` cap, sort, `connectedComponents`).

- [ ] **Step 4:** `npm run test:unit` → PASS. **Step 5: Commit** `git commit -am "feat: islands bounded kNN on the shared feature model with edge evidence"`

---

## Task 11: Evolution export on V2 features with evidence (FR-5, FR-6, FR-7, FR-8)

**Files:**
- Modify: `src/art_islands/evolution.py`
- Test: `tests/test_evolution.py` (extend/adjust)

**Interfaces:**
- Consumes: `features.py` (Task 6), settings sections `features` + `evolution` (Task 3).
- Produces `public/data/evolution.json` version 2 (consumed by Task 12):

```json
{"version": 2,
 "note": "Branches are inferred from date and feature similarity. They do not prove direct influence.",
 "nodes": [{"id": 23, "parent": 7, "evidence": {"score": 0.64, "sharedFeatureCount": 5,
            "topFactors": [{"id": "concept:12", "label": "Cyberpunk", "contribution": 0.31, "source": "direct-concept"},
                           {"id": "entity:50", "label": "Ridley Scott", "contribution": 0.22, "source": "contributor", "relationType": "director"}]}},
           {"id": 7, "parent": null, "evidence": {"score": 0.0, "sharedFeatureCount": 0, "topFactors": []}}]}
```

- [ ] **Step 1: Failing/updated tests** in `tests/test_evolution.py` (they currently build `LineageWork` with `tags`; port to the new loader or feature dicts):

```python
def test_people_and_organizations_never_become_nodes(...)   # fixture with person entity → absent from nodes
def test_parent_strictly_earlier_and_acyclic(...)           # keep existing invariants tests
def test_cross_family_parent_allowed_with_kind_preference(...)  # film child of music work possible, but same-kind wins at equal similarity when kindMismatchFactor < 1
def test_shared_director_connects_undtagged_works(...)      # two works with no shared concepts but same director get an edge (FR-8)
def test_negative_polarity_reduces_parent_score(...)
def test_evidence_exported_with_labels_and_sources(...)     # topFactors have human labels, not ids
def test_undated_works_export_as_roots(...)
def test_deterministic_double_run(...)
def test_export_version_is_2(...)
```

- [ ] **Step 2:** FAIL → **Step 3: Rewrite `evolution.py`.** Keep the module docstring invariants, `CANDIDATE_TAG_DF_CAP`→use `features.CANDIDATE_FEATURE_DF_CAP`, `TEMPORAL_HALF_LIFE_YEARS`, group-by-date processing loop, and `_best_parent` tie-break structure exactly. Changes:
  1. `load_catalogued_works(db, feature_settings)` — one query per source, then assemble per-work `dict[str, Feature]` via `features.extract_features`:
     - works: `select entity_id, release_date from entities where is_catalogued = 1 and entity_family = 'work'` (people/groups/orgs excluded at the source — FR-6 rule 7);
     - kind: `select et.entity_id, d.code from entity_types et join entity_type_definitions d using (entity_type_id) where et.is_primary = 1`; map code→broad kind: film→"film", television_series→"tv", music_album/musical_work→"music", video_game→"game", else "work" (mirror `broadKindForType`);
     - concepts: `select ec.entity_id, ec.concept_id, c.label, cc.label as category_label, ec.weight, ec.polarity from entity_concepts ec join concepts c using (concept_id) join concept_categories cc on cc.concept_category_id = c.concept_category_id order by ec.entity_id, ec.concept_id`;
     - contributors: `select r.source_entity_id, r.target_entity_id, e.label, e.entity_family, t.code, r.weight, r.polarity from entity_relations r join relation_types t using (relation_type_id) join entities e on e.entity_id = r.target_entity_id order by r.source_entity_id, t.code, r.target_entity_id`;
     - advisories: `select a.entity_id, a.advisory_category_id, c.label, a.intensity from entity_advisories a join advisory_categories c on c.advisory_category_id = a.advisory_category_id order by a.entity_id, a.advisory_category_id`.
  2. `compute_lineage` uses `features.build_feature_index` for idf/vectors/norms/postings, `minimum_shared_features` (renamed setting), `kind_mismatch_factor = settings.evolution.kindMismatchFactor`. Candidate postings: only keys with df ≤ cap over strictly-earlier works (keep the two-phase date-group logic verbatim).
  3. `LineageRecord` gains `top_factors: tuple[dict, ...]` (label/source resolved from the work's own Feature metadata); parent scoring dot products keep SIGNED contributions; `similarity <= 0` → skip candidate.
  4. `build_evolution_export` writes the version-2 shape above; undated works appended as roots with empty evidence (unchanged mechanics); note text updated to say "feature similarity".

- [ ] **Step 4:** `pytest tests -q` → PASS.

- [ ] **Step 5: Regenerate the real export and sanity-check the forest shrank toward one mixed structure**

```bash
.venv/bin/art-islands export
python3 - <<'PY'
import json
data = json.load(open("public/data/evolution.json"))
nodes = data["nodes"]
roots = [n for n in nodes if n["parent"] is None]
print("version", data["version"], "nodes", len(nodes), "roots", len(roots))
PY
```
Expected: version 2; root count NOTICEABLY below the pre-change count (contributor + advisory features add connectivity per FR-6 "improving connectivity"; if roots did not drop, investigate before proceeding — do NOT lower thresholds to force it).

- [ ] **Step 6: Commit** — `git commit -am "feat: evolution lineage on V2 features with per-edge evidence (export v2)"`

---

## Task 12: TypeScript evolution lib + chronological layout (FR-5, FR-6)

**Files:**
- Modify: `web/src/lib/evolution.ts`, `web/src/lib/evolutionLayout.ts`, `web/src/lib/types.ts` (EvolutionExport)
- Test: `web/src/lib/evolution.test.ts` (adjust), `web/src/lib/evolutionLayout.test.ts` (create)

**Interfaces:**
- Consumes: `EdgeEvidence`/`EdgeFactor` (declare in `types.ts`, import from features types or redeclare structurally identical), `DomainModel`, `FeatureIndex`.
- Produces:

```ts
// types.ts
export interface EdgeEvidence { score: number; sharedFeatureCount: number; topFactors: EdgeFactor[]; }
export interface EvolutionNode { id: number; parent: number | null; evidence: EdgeEvidence; }
export interface EvolutionExport { version: 2; note: string; nodes: EvolutionNode[]; }
// evolution.ts — signatures change: catalogById+tagIndex params become domain+index
export interface EvolutionChild { id: number; evidence: EdgeEvidence; }
export function buildForest(data: EvolutionExport): EvolutionForest;                 // same struct, children sorted by evidence.score desc then id
export function groupChildren(parentId, children, domain: DomainModel, index: FeatureIndex, settings, expandedGroups): VisibleChildren;
export function revealWork(targetId, forest, domain: DomainModel, index: FeatureIndex, settings): RevealResult | null;
// evolutionLayout.ts
export function buildVisibleForest(forest, domain: DomainModel, index: FeatureIndex, settings, state): VisibleTreeNode[];
export function layoutForest(rootsVisible: VisibleTreeNode[], yearOf: (entityId: number) => number | null): ForestLayout;
```

- [ ] **Step 1: Update evolution.test.ts** — mechanical: nodes get `evidence` instead of `score/shared/topTags`; `broadKind` now comes from `domain.workById.get(id)?.broadKind` (grouping key), remove `tagIndex` fixtures in favor of a small domain+index. Keep all behavioral assertions (placeholder grouping, reveal path, subtree sizing).

- [ ] **Step 2: NEW layout tests** — `evolutionLayout.test.ts`, the FR-6 layout acceptance:

```ts
it("maps years to a shared monotonic column axis across all trees", () => {
  // two roots in different trees with years 1960 and 1980 and children 1970/1990
  // layout x of a node with a LATER year is strictly greater; equal years share x across trees
});
it("children are always right of their parents", ...);
it("undated nodes fall back to one column right of their parent", ...);
it("undated roots go to the trailing undated band at x = 0", ...);
it("stacked trees never overlap vertically and output is deterministic", ...);
```

- [ ] **Step 3:** FAIL → **Step 4: Implement.**
  - `evolution.ts`: replace `EvolutionChild {score,shared,topTags}` with `{id, evidence}`; sorts use `evidence.score`. `groupChildren` broad-kind lookup: `domain.workById.get(child.id)?.broadKind ?? "work"`; similarity via `similarityBetween(index, representative, child.id).similarity`.
  - `evolutionLayout.ts` — `layoutForest(rootsVisible, yearOf)`:
    1. First pass: collect the sorted unique years of ALL visible work nodes (`yearOf(entityId)`), build `columnByYear = Map(year → ordinal)`. One ordinal chronological axis shared by every tree = "one chronological coordinate system"; earlier is always left, and since a parent is strictly earlier, children never collide left of parents.
    2. Run the existing d3 `tree()` per root for ROW placement only (`point.x` → row/y exactly as today).
    3. X: work node with a year → `columnByYear.get(year)! * LEVEL_WIDTH`; work node without a year, and placeholder/fold nodes → `parentX + LEVEL_WIDTH` (root fallback `0`).
    4. Dated trees stack first (offsetY as today); undated ROOTS (no year, no children) are appended after all trees at `x = 0`, one per row — the "separate undated section".
    5. Keep `LEVEL_WIDTH/ROW_HEIGHT/TREE_GAP` constants; deterministic output for identical input (no randomness anywhere).

- [ ] **Step 5:** `npm run test:unit && npm run typecheck` → PASS.

- [ ] **Step 6: Commit** — `git commit -am "feat: evolution evidence types + shared chronological layout axis"`

---

## Task 13: App shell — state, plumbing, loading/error states (FR-3.8, FR-10)

**Files:**
- Modify: `web/src/App.tsx`, `web/src/components/icons.tsx`

**Interfaces:**
- Consumes: `AppData {v2, domain, evolution}` (Task 7), `buildFeatureIndex` (Task 5), `paginate/clampPage` (Task 9), new `Filters` (Task 14).
- Produces the props contract every view uses:
  - Browse: `{ domain, index, ratings, visible, filters, sortMode, page, pageSize, onFiltersChange, onSortModeChange, onPageChange, onPageSizeChange, onOpen, onRate, settings }`
  - Recommendations: `{ domain, index, ratings, settings, onOpen, onRate }`
  - Evolution: `{ data, domain, index, settings, onOpen }`
  - Islands: `{ domain, index, ratings, settings, onOpen, onRate }`
  - Windows: `{ windows, domain, ratings, ... }`

- [ ] **Step 1: State model.** In `App.tsx`:

```tsx
const featureIndex = useMemo(
  () => (data ? buildFeatureIndex(data.domain.works, settings.features) : null),
  [data, settings.features],
);                                              // built once per catalog (§5.3); ratings changes do NOT rebuild it (§5.7)
const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
const [sortMode, setSortMode] = useState("date");
const [page, setPage] = useState(1);
const [pageSize, setPageSize] = useState(0);    // 0 = use settings.browse.defaultPageSize
const effectivePageSize = pageSize || settings.browse.defaultPageSize;

function handleFiltersChange(next: Filters) { setFilters(next); setPage(1); }   // FR-3.6
function handleSortModeChange(mode: string) { setSortMode(mode); setPage(1); }
```
Pagination state lives here, so switching views preserves it (FR-3.8); `visible` = `sortWorks(filterWorks(domain, filters), sortMode, relevance)` memoized; relevance map memoized separately (Task 14 defines both). Header count shows `visible.length` of `domain.works.length`.

- [ ] **Step 2: Error and loading states (FR-10).** Replace `if (error) return <div className="error">…` with an actionable panel:

```tsx
if (error) return (
  <div className="error-panel" role="alert">
    <h2>Data failed to load</h2>
    <p>{error}</p>
    <button type="button" onClick={() => window.location.reload()}>Retry</button>
  </div>
);
if (!data || !featureIndex) return <div className="loading" role="status">Loading catalog…</div>;
```
Missing optional data stays view-local: EvolutionView already renders its regeneration hint; keep it (this distinguishes optional-data absence from full failure).

- [ ] **Step 3: icons.tsx** — add `export function iconForBroadKind(kind: BroadKind): string` mapping `film→` existing film icon name, `tv→` film icon, `music→` music icon, `game→` game icon, `work→` work icon (reuse existing SVG names from `kindIconName`; NO new artwork). Update `KindIcon` in `common.tsx` to accept `{ broadKind, label }: { broadKind: BroadKind; label: string }` (label = `typeLabel`).

- [ ] **Step 4:** `npm run typecheck` passes; app renders (`npm run dev`, check all four tabs). Commit: `git commit -am "feat: app shell on domain model with lifted pagination state and error panel"`

---

## Task 14: BrowseView — V2 filters, relevance sort, pagination UI (FR-3, FR-7, FR-10)

**Files:**
- Modify: `web/src/views/BrowseView.tsx`, `web/src/components/common.tsx`
- Test: filtering/sorting/relevance are pure exports of BrowseView — test in `web/src/lib/browseLogic.test.ts` by importing from the view file (vitest include is `src/**/*.test.ts`, imports of `.tsx` work with the react plugin; if the vitest node env chokes on tsx imports, move `filterWorks/sortWorks/relevanceScores/EMPTY_FILTERS` into a new `web/src/lib/browse.ts` and have the view import them — preferred).

**Interfaces:**
- Produces in `web/src/lib/browse.ts`:

```ts
export interface Filters { q: string; minDate: string; maxDate: string; type: string; conceptId: string; }
export const EMPTY_FILTERS: Filters;
export function filterWorks(domain: DomainModel, filters: Filters): WorkViewModel[];
export function relevanceScores(index: FeatureIndex, works: WorkViewModel[], filters: Filters): Map<number, number> | null; // null when no q/concept
export function sortWorks(works: WorkViewModel[], sortMode: string, relevance: Map<number, number> | null): WorkViewModel[];
```

- [ ] **Step 1: Failing tests** for the logic module:

```ts
it("filters by type, date range, concept, and query over label+concept+contributor names", ...);
it("date/label/kind sorts stay literal and are never affected by relevance", ...);   // FR-7
it("relevance ranks higher-weight matches first", ...);
it("negative-polarity concept matches rank below positive ones", ...);              // signed score sorts last
it("relevance is null without a query or concept filter", ...);
```

- [ ] **Step 2:** FAIL → **Step 3: Implement `browse.ts`:**

```ts
export function filterWorks(domain, filters) {
  const q = filters.q.trim().toLowerCase();
  return domain.works.filter((work) => {
    if (filters.type && work.type !== filters.type) return false;
    if (filters.minDate && (!work.sortDate || work.sortDate < filters.minDate)) return false;
    if (filters.maxDate && (!work.sortDate || work.sortDate > filters.maxDate)) return false;
    if (filters.conceptId && !work.concepts.some((c) => String(c.conceptId) === filters.conceptId)) return false;
    if (!q) return true;
    return (
      work.label.toLowerCase().includes(q) ||
      work.concepts.some((c) => c.label.toLowerCase().includes(q)) ||
      work.contributors.some((c) => c.label.toLowerCase().includes(q))
    );
  });
}
export function relevanceScores(index, works, filters) {
  const q = filters.q.trim().toLowerCase();
  if (!q && !filters.conceptId) return null;
  const scores = new Map<number, number>();
  for (const work of works) {
    let score = 0;
    if (filters.conceptId) score += index.vectors.get(work.id)?.get(`concept:${filters.conceptId}`) ?? 0;
    if (q) {
      for (const feature of index.featuresById.get(work.id) || []) {
        if (feature.label.toLowerCase().includes(q)) score += feature.value;   // signed: negative matches sink
      }
      if (work.label.toLowerCase().includes(q)) score += 2;
    }
    scores.set(work.id, score);
  }
  return scores;
}
export function sortWorks(works, sortMode, relevance) {
  const copy = [...works];
  const byDate = (a, b) => (a.sortDate || "9999-99-99").localeCompare(b.sortDate || "9999-99-99") || a.label.localeCompare(b.label) || a.id - b.id;
  if (sortMode === "relevance" && relevance) {
    return copy.sort((a, b) => (relevance.get(b.id) || 0) - (relevance.get(a.id) || 0) || byDate(a, b));
  }
  if (sortMode === "label") return copy.sort((a, b) => a.label.localeCompare(b.label) || a.id - b.id);
  if (sortMode === "kind") return copy.sort((a, b) => a.typeLabel.localeCompare(b.typeLabel) || a.label.localeCompare(b.label) || a.id - b.id);
  return copy.sort(byDate);
}
```

- [ ] **Step 4: `PaginationControls` in `common.tsx`** (complete component):

```tsx
export function PaginationControls({ page, pageCount, totalItems, pageSize, pageSizeOptions, onPageChange, onPageSizeChange }: {
  page: number; pageCount: number; totalItems: number; pageSize: number; pageSizeOptions: number[];
  onPageChange: (page: number) => void; onPageSizeChange: (size: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Catalog pages">
      <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="Previous page">‹ Prev</button>
      <span className="page-status" aria-live="polite">
        Page {page} of {pageCount} · {totalItems.toLocaleString()} results
      </span>
      <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount} aria-label="Next page">Next ›</button>
      <label className="page-size">
        Per page
        <select value={pageSize} onChange={(e) => onPageSizeChange(Number(e.target.value))} aria-label="Results per page">
          {pageSizeOptions.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
    </nav>
  );
}
```

- [ ] **Step 5: Rewrite BrowseView.** Concrete changes:
  - FilterBar: search input (datalist of top-1000 concept labels), min/max date, TYPE select from `domain.typeOptions` (`{label} ({count})`), CONCEPT select from `domain.conceptById` values sorted by label, SORT select gains `<option value="relevance" disabled={!hasQuery}>Relevance</option>`; auto-switch: when a query/concept is set and sortMode is `date`, App leaves it — do NOT auto-change sort (literal sorts stay literal); "Clear all" button (resets filters+sort, keeps pageSize); active-filter chips row: each non-empty filter renders a chip with an ✕ button (`aria-label="Remove filter …"`). Toolbar `className="filters sticky"`.
  - Table body renders ONLY `paginate(visible, page, effectivePageSize).pageItems` (FR-3.2). Columns: Date (`dateLabel(primaryDate?.value ?? null, primaryDate?.precision ?? 3)`), Work label, Kind icon (`broadKind`/`typeLabel`), Concepts (`ConceptChips` — Task 15's chip list fed with top-6 `work.concepts`), Rating.
  - `PaginationControls` rendered above AND below the table (visible without scrolling; FR-10 "result count and page information together").
  - Empty state unchanged.

- [ ] **Step 6:** `npm run test:unit && npm run typecheck`; manual check via `npm run dev` (2955 works → 60 pages default, filter resets to page 1). Commit: `git commit -am "feat: paginated V2 browse with relevance sorting and filter chips"`

---

## Task 15: Work detail cards (FR-9) + responsive windows

**Files:**
- Create: `web/src/components/WorkDetails.tsx`
- Modify: `web/src/components/windows.tsx`, `web/src/components/common.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `WorkViewModel`, `roleLabel` (Task 4), `formatDuration/advisoryLevel` (Task 4), `RatingButtons`.
- Produces: `export function WorkDetails({ work, domain, rating, onRate, onOpenEntity }: { work: WorkViewModel; domain: DomainModel; rating: number; onRate: RateHandler; onOpenEntity?: (entityId: number) => void })` used by windows and (via row click) all views.

- [ ] **Step 1: Implement `WorkDetails.tsx`.** Structure (every section renders ONLY when it has data — clean omission per FR-9):

```tsx
export function WorkDetails({ work, domain, rating, onRate }: Props) {
  return (
    <div className="entity-body">
      {work.image ? <img className="entity-image" src={imageUrl(work.image)} alt={work.label} loading="lazy" /> : null}
      <div className="entity-main">
        <section className="work-overview">
          <div className="entity-meta">
            <KindIcon broadKind={work.broadKind} label={work.typeLabel} />
            <span>{work.primaryDate ? dateLabel(work.primaryDate.value, work.primaryDate.precision) : "undated"}</span>
            {work.duration ? <span>{work.duration.label}</span> : null}
          </div>
          {work.description ? <p className="work-description">{work.description}</p> : null}
          <RatingButtons id={work.id} label={work.label} rating={rating} onRate={onRate} />
        </section>
        {Object.keys(work.contributorsByRole).length ? <ContributorSection work={work} /> : null}
        {work.measurements.length ? <MeasurementSection work={work} /> : null}
        {(work.ageRatings.length || work.advisories.length || work.restrictions.length) ? <ContentGuideSection work={work} /> : null}
        {work.concepts.length ? <ConceptSections work={work} /> : null}
        {work.identifiers.length ? <ReferenceSection work={work} /> : null}
      </div>
    </div>
  );
}
```
Sub-components (same file):
  - `ContributorSection`: roles in display order `["director","creator","author","screenwriter","composer","lyricist","music_artist","cast_member","voice_actor","performer","producer","production_company","record_label","distributor","publisher","broadcaster"]` then any remaining role alphabetically; each row `<dt>{roleLabel(role)}</dt><dd>` comma-joined names (with `characterLabel` in parentheses when present); >8 names collapse behind a "Show all (N)" toggle button (lazy render, §5.9).
  - `MeasurementSection`: duration first (`work.duration.label`), then others as `{type.replace(/_/g," ")}: {number ?? text}{unit ? ` ${unit}` : ""}`.
  - `ContentGuideSection`: age ratings as `{system}: {certificate}` + `({minimumAge}+)` when set + descriptors chips + edition; advisories as rows `{category} — {advisoryLevel(intensity)}` with a meter-like text (never color-only; the level word is always printed); restrictions as `{type.replace(/_/g," ")} · {countryCode} {startDate}–{endDate}: {reason}`. NO raw JSON anywhere.
  - `ConceptSections`: iterate `work.conceptsByCategory` in domain category order (genre, theme, keyword, style, mood, motif, movement, setting, subject, technique, trope, audience, format, franchise, language, country, period, other — i.e., genre/theme first, `other` LAST); each category collapsible (`<details>` with `<summary>{categoryLabel} ({n})</summary>` — keyboard accessible for free); chips show `{label} {weight}` with class `negative` and a `−` prefix when `polarity < 0` plus `aria-label="{label}, excluded"`; only the first 12 chips per category render until expanded ("Show all (N)" toggle).
  - `ReferenceSection`: `work.identifiers` as links `{label}` → `url`, `target="_blank" rel="noreferrer"`; plain span when url empty. De-dupe by label+url.
  - Rewire `TagList`→ delete; `tagEntries` → delete (Task 21 confirms no users remain). Add small `ConceptChips({ concepts, limit })` used by BrowseView (Task 14).

- [ ] **Step 2: windows.tsx** — `FloatingEntityWindows` consumes `domain` (`domain.workById.get(win.id)`); header subtitle = `[dateLabel(...), work.typeLabel]`; body = `<WorkDetails …/>`. Responsive (FR-9): the window `<article>` gets `className={isNarrowScreen() ? "entity-window sheet" : "entity-window"}` re-evaluated via a `matchMedia` listener hook `useIsNarrow()` (add in windows.tsx); when narrow: position styles omitted (CSS pins it), drag already disabled.

- [ ] **Step 3: styles.css additions** (append):

```css
.entity-window.sheet {
  left: 0 !important; top: auto !important; bottom: 0; right: 0;
  width: 100%; max-width: none; max-height: 85vh; border-radius: 12px 12px 0 0;
}
.entity-window.sheet .window-header { position: sticky; top: 0; }
.work-section { margin-top: 12px; }
.work-section summary { cursor: pointer; font-weight: 600; }
.contributor-roles dt { font-weight: 600; margin-top: 6px; }
.chip.negative::before { content: "− "; }
.pagination { display: flex; gap: 12px; align-items: center; padding: 8px 16px; flex-wrap: wrap; }
.filters.sticky { position: sticky; top: 0; z-index: 5; background: inherit; }
.filter-chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 4px 16px; }
.error-panel { max-width: 560px; margin: 15vh auto; text-align: center; }
:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; } }
```
(Adjust color variables to match the existing palette in styles.css; do not invent a new look.)

- [ ] **Step 4:** typecheck + `npm run dev` manual pass: open a film (duration, director, cast, advisories, grouped concepts, IMDb link), a music release, a work with almost no data (clean omission). Narrow viewport (<720px): sheet from bottom, obvious close, no dragging needed.

- [ ] **Step 5: Commit** — `git commit -am "feat: full V2 work detail cards with responsive sheet mode"`

---

## Task 16: RecommendationsView explanations (FR-10)

**Files:**
- Modify: `web/src/views/RecommendationsView.tsx`

- [ ] **Step 1:** Port to `scoreRecommendations(domain, index, ratings, settings)` (Task 8). "Why" cell renders structured evidence instead of a sentence:

```tsx
<td className="why-cell">
  {result.positive.slice(0, 2).map((f) => (
    <span key={f.id} className="evidence positive">{factorPhrase(f)}</span>
  ))}
  {result.negative.length ? (
    <span className="evidence negative">− {factorPhrase(result.negative[0])}</span>
  ) : null}
</td>
```
`.evidence.negative` styled distinctly AND prefixed with "−" (not color-only). Keep score/date/kind/rating columns; rows keep `rowInteractionProps` so they open the enhanced card (already wired). Empty states: no likes → existing message, extend to "Like several works first — try Browse. Recommendations appear once at least one liked work shares features with unrated works."

- [ ] **Step 2:** typecheck; manual dev check; commit `git commit -am "feat: recommendation rows show positive and negative evidence"`.

---

## Task 17: IslandsView — evidence tooltips, help text (FR-4, FR-10)

**Files:**
- Modify: `web/src/views/IslandsView.tsx`

- [ ] **Step 1:** Port to `buildIslandsGraph(domain, index, deferredRatings, settings)`. `explanationFor` uses node `topFactors` (`factorPhrase`) and edge `topFactors` instead of tag names.
- [ ] **Step 2:** Edge accessibility: switch edges to `focusable: true` and add `aria-label` per edge: `` `${labelOf(source)} ↔ ${labelOf(target)}: similarity ${edge.similarity.toFixed(2)}, ${edge.topFactors.map(f => f.label).join(", ")}` ``; explicit edges: `` `${relationTypeLabel} relation` ``. Keep the legend exactly (liked/disliked/recommended/explicit/inferred). Add to the panel: `<p className="graph-help">Edges connect each work to at most {settings.islands.maxInferredNeighborsPerNode} nearest neighbors with similarity ≥ {settings.islands.minimumSimilarity}. Dashed edges are explicit catalog relations.</p>`.
- [ ] **Step 3:** Focus improvement: the existing `onFocusComponent` fit stays; wrap `fitView` durations in `motionDuration(300)`.
- [ ] **Step 4:** typecheck + manual check (like 2 disjoint works → 2 islands; hover/focus an edge shows evidence). Commit `git commit -am "feat: islands evidence tooltips and knn help text"`.

---

## Task 18: EvolutionView — evidence edges with tooltips and arrows (FR-5, FR-6)

**Files:**
- Modify: `web/src/views/EvolutionView.tsx`, `web/src/styles.css`

**Interfaces:** Consumes `EdgeEvidence` on `VisibleTreeNode.edge` (Task 12), `factorPhrase` (Task 5), `motionDuration`.

- [ ] **Step 1: Custom evidence edge.** Add to EvolutionView.tsx:

```tsx
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, MarkerType } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

interface EvidenceEdgeData extends Record<string, unknown> {
  evidence: EdgeEvidence; earlierLabel: string; laterLabel: string;
}
function EvidenceEdge(props: EdgeProps) {
  const [open, setOpen] = useState(false);
  const data = props.data as EvidenceEdgeData;
  const [path, labelX, labelY] = getSmoothStepPath(props);
  const strongest = data.evidence.topFactors[0];
  return (
    <>
      <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} />
      {/* invisible fat path for hover/focus target */}
      <path d={path} className="edge-hit" tabIndex={0} role="img"
        aria-label={`${data.earlierLabel} to ${data.laterLabel}, similarity ${data.evidence.score.toFixed(2)}, ${data.evidence.sharedFeatureCount} shared features`}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} />
      <EdgeLabelRenderer>
        <div className="edge-label nodrag nopan" style={{ transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)` }}>
          {strongest ? <span className="edge-label-chip">{strongest.label}</span> : null}
          {open ? (
            <div className="edge-tooltip" role="tooltip">
              <strong>{data.earlierLabel} → {data.laterLabel}</strong>
              <div>Similarity: {data.evidence.score.toFixed(2)} · {data.evidence.sharedFeatureCount} shared features</div>
              <ul>{data.evidence.topFactors.map((f) => <li key={f.id}>{factorPhrase(f)}</li>)}</ul>
            </div>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
const edgeTypes = { evidence: EvidenceEdge };
```

- [ ] **Step 2: Wire edges.** In the `edges` memo: `type: "evidence"`, `markerEnd: { type: MarkerType.ArrowClosed }`, `focusable: false` (the inner hit path handles focus), `data: { evidence: childNode.edge!.evidence ?? EMPTY_EVIDENCE, earlierLabel: labelOf(parent), laterLabel: labelOf(child) }` — parent (earlier) is always the edge SOURCE, so arrows point earlier → later. Edges into placeholder/fold nodes keep `type: "smoothstep"` without evidence.
- [ ] **Step 3: Zoom-dependent labels.** In `EvolutionCanvas`, `const { zoom } = useViewport();` and set `data-zoom-low={zoom < 0.7}` on the wrapper div; CSS: `[data-zoom-low="true"] .edge-label-chip { display: none; }` (tooltips still work via focus at any zoom).
- [ ] **Step 4: Chronological canvas wiring.** `layoutForest(visibleForest, (id) => domain.workById.get(id)?.year ?? null)`. Node tooltip text: replace tag names with `node.edge.evidence.topFactors.map(factorPhrase).join("; ")`. Update panel disclaimer: "Branches are inferred from date and feature similarity — direction shows earlier → later, not proven influence." Wrap `fitView`/`setCenter` durations in `motionDuration`.
- [ ] **Step 5: styles.css** — `.edge-hit { stroke: transparent; stroke-width: 16; fill: none; } .edge-hit:focus-visible { stroke: rgba(255,255,255,0.15); } .edge-tooltip { position: absolute; z-index: 10; …panel styling…; } .edge-label-chip { font-size: 10px; …chip styling…; }`
- [ ] **Step 6:** typecheck + manual: hover an edge → tooltip with direction/score/factors; Tab reaches edges and shows the tooltip; arrows visible; roots share one time axis; undated section at the bottom. Commit `git commit -am "feat: explainable evolution edges with keyboard-accessible tooltips"`.

---

## Task 19: Cross-view UI polish pass (FR-10 remainder)

**Files:** `web/src/styles.css`, `web/src/App.tsx`, small touch-ups in views

- [ ] **Step 1:** Walk the FR-10 checklist and fix what remains; verify each in the dev server at 1440px / 820px / 390px widths:
  - Active view tab visually clear (existing `.tab.active` — strengthen contrast if weak).
  - No scroll resets: table scroll preservation exists; verify graphs keep viewport on view switches (React Flow instances unmount — acceptable; state like expandedNodes already persists via sessionStorage).
  - Consistent buttons/inputs: audit styles.css; unify paddings/radii.
  - Mobile filters: `.filters` wraps (`flex-wrap: wrap`), selects full-width under 720px.
  - Tables: `.table-wrap { overflow-x: auto; }` with rating buttons column kept visible (`position: sticky; right: 0` on `.rating-cell` if needed).
  - All icon-only buttons have `aria-label` (grep `icon-button` usages).
  - Focus states visible (`:focus-visible` rule from Task 15).
- [ ] **Step 2:** `npm run build && npm run test:e2e` — expect several e2e failures against the NEW UI; that's Task 20's input, do not fix blind. Commit style-only work: `git commit -am "style: responsive and accessibility polish across views"`.

---

## Task 20: E2E suite for the migrated app (spec §7)

**Files:**
- Modify: `e2e/helpers.ts`, `e2e/app.spec.ts`, `e2e/evolution.spec.ts`, `e2e/islands.spec.ts`
- Create: `e2e/browse.spec.ts`, `e2e/workcard.spec.ts`

- [ ] **Step 1: helpers.ts** — port to V2 data:

```ts
export interface CatalogEntry { id: number; label: string; date: string | null; conceptIds: Set<number>; }
export async function fetchCatalog(page: Page): Promise<CatalogEntry[]> {
  const [catalog, concepts] = await Promise.all([
    page.request.get(`${BASE}data/v2/catalog.json`).then((r) => r.json()),
    page.request.get(`${BASE}data/v2/concepts.json`).then((r) => r.json()),
  ]);
  const byEntity = new Map<number, Set<number>>();
  for (const ec of concepts.entityConcepts) {
    let set = byEntity.get(ec.entityId);
    if (!set) byEntity.set(ec.entityId, (set = new Set()));
    set.add(ec.conceptId);
  }
  return catalog.map((c: { id: number; label: string; compatibilityDate?: string }) => ({
    id: c.id, label: c.label, date: c.compatibilityDate ?? null, conceptIds: byEntity.get(c.id) ?? new Set(),
  }));
}
export function disjointPair(catalog: CatalogEntry[]): [CatalogEntry, CatalogEntry] { /* same logic over conceptIds */ }
```

- [ ] **Step 2: `e2e/browse.spec.ts`** (FR-3 acceptance + §7 e2e 1–3):

```ts
test("browse mounts at most one page of rows and paginates", async ({ page }) => {
  await openApp(page);
  await expect(page.locator("table tbody tr")).toHaveCount(50);
  await expect(page.getByText(/Page 1 of \d+/).first()).toBeVisible();
  await page.getByRole("button", { name: "Next page" }).first().click();
  await expect(page.getByText(/Page 2 of/).first()).toBeVisible();
});
test("changing page size remounts the right row count", ...);       // select 25 → 25 rows; 100 → 100 rows
test("filtering resets to page 1 and filters the whole catalog", async ({ page }) => {
  // go to page 3, type a query that matches a work NOT on the first unfiltered page, expect Page 1 + match visible
});
test("pagination state survives switching views", ...);             // page 2 → Islands → Browse → still page 2
```

- [ ] **Step 3: `e2e/workcard.spec.ts`** (§7 e2e 4–7, 12): open a known film row (find via fetchCatalog a work whose id has contributors+duration in `v2/catalog.json` — e.g. pick the first catalog item with a `duration` measurement and a `director` contributor at runtime); assert the card shows a Contributors role heading (e.g. "Director"), a duration matching `/\d+ h \d+ min|\d+ min/`, a content-guide section when advisories exist, grouped concept `<summary>` headings, and external reference links. Narrow-screen test: `page.setViewportSize({width: 390, height: 800})`, open row, expect `.entity-window.sheet` visible and close button clickable without drag.

- [ ] **Step 4: Update existing specs.**
  - `app.spec.ts` "data requests use the Pages base path": update expected fetches (v2 files instead of catalog.json/tags.json).
  - `evolution.spec.ts`: keep placeholder/reveal/session tests (selectors mostly unchanged); ADD edge tooltip test: `await page.locator(".edge-hit").first().focus(); await expect(page.locator(".edge-tooltip")).toBeVisible(); await expect(page.locator(".edge-tooltip")).toContainText("Similarity:");` and a hover variant (§7 e2e 9, keyboard + hover both).
  - `islands.spec.ts`: keep all; ADD bounded-edges assertion: `expect(await page.locator(".react-flow__edge").count()).toBeLessThanOrEqual(500);` and legend presence check.
  - Recommendation explanation test (§7 e2e 8) in `app.spec.ts` or new: seed ratings, open Recommendations, expect `.evidence.positive` visible with text matching `/Shared|Same/`, and a row click opens the work card.

- [ ] **Step 5:** `npm run build && npm run test:e2e` → ALL PASS (iterate on selectors/UI bugs found; this is where real integration issues surface — fix them in the view code, not by weakening assertions).

- [ ] **Step 6: Commit** — `git commit -am "test: e2e coverage for pagination, work cards, edge evidence"`

---

## Task 21: Legacy removal, CI, docs, final validation (FR-1 rule 3, §5.10, DoD)

**Files:**
- Delete: `web/src/lib/tagIndex.ts`
- Modify: `web/src/lib/types.ts` (drop legacy types), `web/src/lib/format.ts` (drop `KIND_LABELS`/`kindLabel`/`externalUrl`/`RefEntry`), `.github/workflows/ci.yml`, `README.md`
- Keep: Python legacy export (`model.export_static_data`) — it still generates `catalog.json`/`tags.json`/`entities-lookup.json` for external/back-compat use AND `evolution.json`; document this as the isolated compatibility layer.

- [ ] **Step 1: Delete dead code.** Remove `tagIndex.ts`; grep for leftovers of `CatalogItem`, `TagEntry`, `LinkEntry`, `Tag `, `Lookup`, `tagEntries`, `TagList`, `kindLabel`, `broadKind(` (legacy numeric) — delete the types and any straggler imports. `npm run typecheck` is the executioner here: it must pass with zero legacy references in `web/src`.
- [ ] **Step 2: Payload measurement (§5.10).** Record before/after numbers in the README (or the ADR): legacy fetch set (catalog+tags+lookup ≈ 4.2 MB) no longer downloaded; v2 set slimmed in Task 2. Run:

```bash
du -h public/data/*.json public/data/v2/*.json
```
and note the total the app now fetches. If `advisories.json` (>5 MB) is still the dominant cost, note "chunked static exports" as the documented follow-up (explicitly a non-blocking follow-up per FR-3 performance note).
- [ ] **Step 3: CI.** In `ci.yml`: after "Rebuild static exports" add `- name: Rebuild v2 static exports` / `run: python -m art_islands db-v2 export`; keep the LFS + quick_check steps from Task 1; ensure "Validate generated JSON" also globs `public/data/v2/*.json`. Verify the FR-2 acceptance command sequence works from a clean state:

```bash
sqlite3 data/art-islands.sqlite "PRAGMA quick_check;"
.venv/bin/art-islands export
.venv/bin/art-islands db-v2 export
npm run build
```
- [ ] **Step 4: README + docs.** Update: views description (feature-based recommendations/evolution/islands), LFS setup (from Task 1), the export commands, link `docs/feature-model.md` and the ADR, describe `data/settings.json` new sections, note that legacy JSON exports are generated for compatibility but not used by the app.
- [ ] **Step 5: Full validation (Definition of Done):**

```bash
.venv/bin/python -m pytest tests -q
npm run typecheck
npm run test:unit
npm run build
npm run test:e2e
```
All green. Commit: `git commit -am "chore: remove legacy tag pipeline from frontend, update CI and docs"`.

- [ ] **Step 6: Definition-of-Done sweep.** Re-read spec §8 line by line against the branch; every bullet must be checkable. Then use superpowers:finishing-a-development-branch (merge/PR decision belongs to the user).

---

## Self-review notes (already applied)

- **Spec coverage:** FR-1→Tasks 4/7/21; FR-2→Task 1(+2 quick_check); FR-3→Tasks 9/13/14/20; FR-4→Task 10(+17); FR-5→Tasks 11/12/18; FR-6→Tasks 11/12/18; FR-7→Tasks 3/5/6/8/14; FR-8→Tasks 5/6/8/11; FR-9→Tasks 2/4/15; FR-10→Tasks 13–19; §4→Tasks 5/6 + `docs/feature-model.md`; §5→index memoization (13), DF caps (5/10/11), pagination (9/14), payload slimming (2/21); §6→Task 3; §7→per-task tests + Task 20; §9 non-goals respected (no forced single tree, no all-pairs, no history rewrite, no backend).
- **Known judgment calls (documented so the executor doesn't re-litigate):** advisories double as the content-guide feature source (the `entity_content_guide_dimensions` table stays unexported — 53k rows of JSON that would bloat the payload; advisories carry the same category+intensity signal); contributor multiplier is chosen by ROLE (family only affects the `source` label); `main_subject`/`depicts` contribute no inherited features; Evolution chronology uses an ordinal year-column axis (strict linear years would overlap century-dense regions).
- **Type consistency:** `EdgeFactor`/`EdgeEvidence` are declared once (features.ts/types.ts) and reused by recommendations, islands, evolution, and views; settings key names match `data/settings.json` exactly; `maxInferredNeighborsPerNode` and `minimumSharedFeatures` are the only names used after Task 3.



