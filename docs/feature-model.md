# Canonical feature and similarity semantics

One specification for Python (build-time Evolution export) and TypeScript
(Browse relevance, Recommendations, Islands). Golden fixtures in
`shared/fixtures/feature-golden.json` verify that both implementations agree;
regenerate them with `python tools/generate_feature_golden.py` after any
intentional semantic change.

Implementations: `src/art_islands/features.py` and `web/src/lib/features.ts`.

## Feature keys

- `concept:<conceptId>` — direct work concept. Source `direct-concept`.
- `entity:<entityId>` — one-hop contributor/organization inheritance. Source
  `contributor`, or `organization` when the target entity family is
  organization/group. No propagation beyond one hop, ever; people, groups,
  and organizations never become graph nodes themselves.
- `advisory:<categoryId>` — content-guide (advisory) profile. Source
  `content-guide`.

## Values

```
magnitude  = clamp(weight / 100, 0, 1)          (advisories use intensity)
sign       = -1 if polarity < 0 else +1         (advisories always +1)
base       = magnitude × sign × sourceMultiplier
final      = base × idf(key)
idf(key)   = ln(1 + N / df(key)) over all catalogued works
```

Source multipliers come from `settings.features`. Role → multiplier map
(roles not listed contribute NO inherited feature):

| Roles                                                                | Multiplier               |
| -------------------------------------------------------------------- | ------------------------ |
| creator, composer, lyricist, music_artist                             | `creatorMultiplier`      |
| director                                                              | `directorMultiplier`     |
| author, screenwriter                                                  | `authorMultiplier`       |
| producer                                                              | `producerMultiplier`     |
| cast_member, voice_actor, performer                                   | `performerMultiplier`    |
| production_company, record_label, distributor, publisher, broadcaster | `organizationMultiplier` |
| Direct concepts                                                       | `directConceptMultiplier`|
| Advisories (content guide)                                            | `contentGuideMultiplier` |

When the same target entity appears through several roles, keep the single
feature with the largest |value| (ties: the first role in ascending role-code
order wins). This per-source cap stops high-degree entities from stacking
evidence.

## Similarity

```
cosine(a, b) = Σ_k a[k]·b[k] / (‖a‖·‖b‖) over final values
```

Opposite signs subtract, so opposite polarity reduces compatibility.
`sharedFeatureCount` = number of keys present in both vectors.
**A similarity ≤ 0 never creates an inferred edge.**
`topFactors` = shared keys sorted by contribution desc (ties: key asc), top 3,
each carrying a human-readable label and its source.

## Candidate generation

An inverted index maps feature key → work ids. Keys with document frequency
> 150 are still scored but never used for candidate generation, which keeps
fan-out bounded and forbids all-pairs comparison loops.

## Determinism

All sorts specify total orders (value/contribution desc, then key/id asc);
identical inputs and settings always produce identical outputs in both
languages.
