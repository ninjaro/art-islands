# ADR 0001: Store data/art-islands.sqlite in Git LFS

Date: 2026-07-07
Status: Accepted

## Context

- Current size: 76,910,592 bytes (~73 MiB) as of 2026-07-07.
- Growth: 13 MB → 32 MB → 77 MB across the three commits that have touched it
  (`init` → `db migration` → `some numbers`). It is expected to keep growing as
  new works and V2 domain tables (concepts, advisories, content-guide
  dimensions) are enriched.
- Update frequency: every approved data batch — the
  `.github/workflows/data-batch.yml` workflow applies issue-driven corrections
  and opens a PR with a modified database — plus manual curation commits.
- Git impact so far: ~35 MB of pack data for three versions (packed blob sizes
  6.2 / 13.6 / 15.6 MB). SQLite binaries delta poorly, so each future update
  adds roughly a full re-compressed blob (~15 MB+ at the current size) to the
  permanent history of every clone. Ten updates ≈ +150 MB.
- GitHub rejects individual files over 100 MB outright; the database is at
  ~77 % of that limit, so a plain-Git workflow would eventually hard-fail a
  push with no easy recovery.
- Git LFS free tier provides 1 GB storage and 1 GB/month bandwidth — years of
  headroom at this size. CI and clones fetch only the current version instead
  of the full blob history.

## Decision

Track `data/*.sqlite` with Git LFS starting from the `migration` branch
onward. Do NOT rewrite existing history (explicitly out of scope per the
project spec); the three pre-LFS blobs remain in normal Git.

## Consequences

- Contributors need `git lfs install` once (documented in the README).
- All GitHub Actions checkouts must pass `lfs: true`, and CI validates that it
  received a real SQLite database rather than an LFS pointer
  (`SQLite format 3` magic + `PRAGMA quick_check`). The Python exporters also
  run `PRAGMA quick_check` before writing any static exports.
- The SQLite file is never served through GitHub Pages; the app keeps loading
  only the generated JSON exports from `public/data/`.
