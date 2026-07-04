# Art Islands

A static catalog explorer for films, music releases, and other works. A Python
CLI owns the editable SQLite database and generates static JSON exports; a
small React + Vite frontend renders four views — **Browse**, **Recommendations**,
**Evolution**, and **Islands** — with all personal ratings stored purely in the
browser's localStorage. There is no backend.

* **Browse** — filterable, sortable catalog table with local like/dislike ratings.
* **Recommendations** — tag-overlap recommendations derived from your local ratings.
* **Evolution** — an inferred temporal similarity forest of catalogued works.
  Branches are inferred from date and tag similarity; they do not prove direct influence.
* **Islands** — a graph of your rated works plus recommended works, split into
  connected components. Disconnected islands are expected and never joined artificially.

## Local installation

Requires Python ≥ 3.11 and Node ≥ 20.

```sh
python -m venv .venv
.venv/bin/pip install -e . pytest
npm ci
```

## Local development

```sh
npm run dev          # Vite dev server at http://localhost:5173/art-islands/
```

The dev server serves the JSON exports from `public/data/` under the same
`/art-islands/` base path used on GitHub Pages.

## Python export

The SQLite database `data/art-islands.sqlite` is the editable source of truth.
Regenerate all static exports (catalog, tags, lookup, settings, and the
Evolution lineage) after any data change:

```sh
.venv/bin/art-islands export
```

Tunable thresholds (recommendation weights, Evolution lineage and grouping
settings, Islands graph caps) live in `data/settings.json` and are exported to
`public/data/settings.json`. Other CLI commands: `migrate`, `build`, `enrich`,
`tag set`, `config show|set`, `batch`, `serve-static`.

## Production build

```sh
npm run build        # writes the static site to dist/ with base /art-islands/
npm run preview      # serve the production build locally
```

## Tests

```sh
.venv/bin/python -m pytest tests -q   # Python: model, CLI, evolution lineage, batch parser
npm run typecheck                     # TypeScript checks
npm run test:unit                     # Vitest: recommendation, evolution, islands algorithms
npm run test:e2e                      # Playwright browser tests (run npm run build first)
```

## Issue batch format

Data corrections can be proposed by opening a **Data correction batch** issue
containing exactly one batch: either an attached `.json`/`.jsonl` file
(uploaded to GitHub so it becomes a `github.com/user-attachments/files/…`
link) or one fenced ```json block. A batch is declarative data — scripts,
shell fragments, and SQL are rejected and never executed.

```json
{
  "version": 1,
  "operations": [
    {
      "op": "update_entity",
      "entityId": 123,
      "set": {
        "label": "Corrected title",
        "releaseDate": "1981-01-01",
        "datePrecision": 1,
        "entityKind": 2,
        "imageRef": null,
        "isCatalogued": true
      }
    },
    { "op": "set_external_ref", "entityId": 123, "kind": "wikidata", "value": "Q12345" },
    { "op": "remove_external_ref", "entityId": 123, "kind": "imdb", "value": "tt0000000" },
    { "op": "set_entity_tag", "entityId": 123, "tagId": 456, "weight": 75, "polarity": 0 },
    { "op": "remove_entity_tag", "entityId": 123, "tagId": 789 }
  ]
}
```

Every operation is validated against the database before anything is applied:
entity and tag existence, date format and precision, enum and range checks,
external-reference formats, duplicate or conflicting operations, and
foreign-key safety. JSONL batches use one operation object per line with an
optional `{"version": 1}` header line.

## Approval-label workflow

Opening an issue runs nothing. After review, a maintainer adds the
`data-batch-approved` label, which triggers `.github/workflows/data-batch.yml`
(manual reruns via *workflow dispatch* with the issue number). The workflow
checks out `main`, extracts and validates the batch, applies it to
`data/art-islands.sqlite`, rebuilds all exports, runs foreign-key checks and
the Python/JavaScript test suites, builds the React app, and force-updates the
branch `data-batch/issue-N` with a pull request. Re-running the same issue
updates the existing branch and PR instead of creating duplicates. The PR is
never auto-merged, and the bot comments the validation result, operation
counts, and PR link back on the issue.

## GitHub Pages deployment

`.github/workflows/pages.yml` deploys the production build to GitHub Pages
using the official Pages actions and the `github-pages` environment. It runs
only for `main` (push or manual dispatch) and uploads `dist/` as the Pages
artifact; built output is not committed to the repository. The site is served
under the project path `/art-islands/`, and all asset and data URLs derive
from that base path.
