# Art Islands DB v2 Migration Workspace

This directory contains one-off migration tooling, reports,
checkpoints, cache schemas, and reproduction commands for the
offline-first Art Islands database v2 migration.

Useful commands:

```sh
art-islands db-v2 inventory
art-islands db-v2 build-index --resume --limit 1000
art-islands db-v2 build-people-cache --qid Q873 --limit 1
art-islands db-v2 migrate --replace
art-islands db-v2 export
art-islands db-v2 validate
```

Large generated caches and checkpoints are ignored by git.
Source files under `../layers/` are read-only inputs.

Run a full unbounded layer index intentionally; the local
`other_creative_work.jsonl` source is large and should only be included with
`--include-other` when the migration phase needs it.
