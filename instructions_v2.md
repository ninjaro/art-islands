# Technical Specification: Complete the V2 Migration and Extend Art Islands

## Repository and Branch

Repository: `ninjaro/art-islands`

Base branch: `migration`

All implementation work must start from the existing `migration` branch. Do not start from `main` and do not discard or recreate the migration work that is already present.

A new implementation branch may be created from `migration`.

---

## 1. Objective

Complete the migration of Art Islands to the new V2 domain model and update the frontend to use the migrated data correctly.

The work must also improve:

* Catalog performance and pagination
* Recommendation quality
* Tag weighting and polarity handling
* Evolution graph structure and explainability
* Islands graph density and layout
* Related people and organization metadata
* Parental/content guide presentation
* Work detail cards
* General UI and UX quality

The application must remain a static React/Vite application without introducing a mandatory backend service.

---

## 2. Current State

The `migration` branch already contains:

* A cleaned SQLite domain database
* V2 static data exports
* V2 TypeScript interfaces
* V2 loading logic in `web/src/lib/data.ts`
* Entity types, relations, concepts, measurements, age ratings, advisories, and restrictions
* Existing Browse, Recommendations, Evolution, and Islands views

However, the existing views still primarily consume the legacy structures:

* `catalog.json`
* `tags.json`
* Legacy `CatalogItem.tags`
* Legacy entity links and kinds

The V2 data is loaded into `AppData.v2`, but it is not yet the primary data source for the UI or recommendation and graph algorithms.

Relevant files include:

* `src/art_islands/v2.py`
* `web/src/lib/data.ts`
* `web/src/lib/types.ts`
* `web/src/lib/recommendations.ts`
* `web/src/lib/tagIndex.ts`
* `web/src/lib/islands.ts`
* `web/src/lib/evolution.ts`
* `web/src/views/BrowseView.tsx`
* `web/src/views/RecommendationsView.tsx`
* `web/src/views/EvolutionView.tsx`
* `web/src/views/IslandsView.tsx`
* `web/src/components/windows.tsx`

---

# 3. Functional Requirements

## FR-1. Complete the V2 Data Migration

### Requirement

Finish the frontend migration so that the application uses the V2 domain exports as its canonical domain model.

The UI should not directly combine raw V2 export objects in multiple components. Introduce a normalized frontend domain layer that converts the V2 exports into stable view models.

### Recommended frontend models

At minimum, introduce a normalized work model containing:

```ts
interface WorkViewModel {
  id: number;
  label: string;
  description?: string;
  family: string;
  image?: string;

  dates: NormalizedDate[];
  primaryDate?: NormalizedDate;

  concepts: NormalizedConceptAssignment[];
  conceptsByCategory: Record<string, NormalizedConceptAssignment[]>;

  contributors: NormalizedContributor[];
  contributorsByRole: Record<string, NormalizedContributor[]>;

  measurements: NormalizedMeasurement[];
  duration?: NormalizedDuration;

  ageRatings: NormalizedAgeRating[];
  advisories: NormalizedAdvisory[];
  restrictions: NormalizedRestriction[];

  identifiers: NormalizedIdentifier[];
}
```

The exact interface may differ, but UI components must not repeatedly reconstruct this information from raw arrays.

### Migration rules

1. V2 data must become the primary source for:

   * Entity labels and descriptions
   * Entity families and types
   * Concepts and concept categories
   * Contributor and organization relations
   * Measurements and duration
   * Age ratings
   * Content advisories
   * Restrictions
   * External identifiers

2. A temporary legacy compatibility adapter may remain during implementation.

3. Once functional parity is reached, views must not depend on legacy tag tuples where equivalent V2 concept data exists.

4. Missing optional V2 data must not crash the application.

5. Export validation must fail clearly when required V2 files are absent or structurally invalid.

6. Generated data must remain deterministic for identical database input.

### Acceptance criteria

* Browse, Recommendations, Evolution, Islands, and entity details operate using normalized V2-backed work data.
* The application does not show conflicting legacy and V2 values for the same field.
* Missing advisories, measurements, contributors, or descriptions produce valid empty states.
* `npm run typecheck`, unit tests, E2E tests, and the production build pass.

---

## FR-2. Evaluate and Implement Appropriate SQLite Storage

### Requirement

Evaluate whether `data/art-islands.sqlite` should be moved to Git Large File Storage.

Because SQLite is a binary file, normal Git history may grow significantly whenever the database changes, even when the logical data change is small.

### Decision procedure

Record the following in a short architecture decision document:

* Current database size
* Expected database growth
* Frequency of database updates
* Current Git repository growth caused by database commits
* Git LFS storage and bandwidth implications
* CI and contributor workflow implications

### Preferred outcome

Use Git LFS when the SQLite database is large or expected to change regularly.

Suggested tracking rule:

```gitattributes
data/*.sqlite filter=lfs diff=lfs merge=lfs -text
```

### Implementation requirements when LFS is enabled

1. Add and commit `.gitattributes`.
2. Track the active SQLite database through Git LFS.
3. Ensure all GitHub Actions checkouts download the actual LFS object.
4. Validate that CI receives a real SQLite database rather than an LFS pointer file.
5. Run `PRAGMA quick_check` or an equivalent validation before exporting data.
6. Update the local setup documentation.
7. Do not serve the SQLite file directly through GitHub Pages.
8. Continue serving normal generated JSON files through the static application.
9. Do not rewrite the complete repository history without explicit approval.
10. Starting LFS tracking from the migration branch onward is acceptable when history rewriting is not approved.

### Alternative

The database may remain in regular Git only when the decision document demonstrates that its size and update frequency do not create a meaningful repository maintenance problem.

### Acceptance criteria

A fresh clone and a clean CI job must be able to:

```sh
sqlite3 data/art-islands.sqlite "PRAGMA quick_check;"
.venv/bin/art-islands export
.venv/bin/art-islands db-v2 export
npm run build
```

The commands must operate on the actual database, not an LFS pointer.

---

## FR-3. Add Pagination to Catalog Tables

### Requirement

Do not render the entire filtered catalog as table rows at the same time.

Implement pagination for Browse and any other view that may display a large tabular result set.

### Behavior

1. Filtering and sorting must be applied to the complete dataset before pagination.
2. Only the current page of rows may be mounted in the DOM.
3. Default page size: `50`.
4. Supported page sizes:

   * 25
   * 50
   * 100
5. Pagination controls must include:

   * Previous page
   * Next page
   * Current page
   * Total page count
   * Total result count
   * Page-size selector
6. Changing a filter, search query, or sort mode must reset the current page to page 1.
7. The current page must be clamped when the number of results decreases.
8. Pagination state should be preserved when switching between application views during the same session.
9. Keyboard and screen-reader navigation must be supported.

### Performance note

Client-side pagination reduces DOM rendering cost but does not reduce the initial JSON download.

After implementing UI pagination, measure the remaining loading cost. If the initial catalog payload remains a bottleneck, add chunked static exports or a compact catalog index as a separate follow-up optimization.

Do not introduce fake server-side pagination when there is no backend.

### Acceptance criteria

* A result containing thousands of works mounts no more than the selected page size.
* Search and filters still operate across the entire catalog.
* Pagination does not lose ratings, filters, or sorting state.
* E2E tests cover moving between pages and resetting the page after filtering.

---

## FR-4. Keep the Islands Graph Bounded with up-to-K Nearest Neighbors

### Requirement

The Islands graph must not display every possible similarity edge.

Use a configurable up-to-K nearest-neighbor graph for inferred similarity edges.

The migration branch already contains a bounded k-NN union implementation. Preserve it, verify it, and extend it to use the new common weighted feature model.

### Algorithm

For every displayed work node:

1. Generate candidates through an inverted feature index.
2. Do not compare every displayed node against every other node.
3. Calculate weighted, polarity-aware similarity.
4. Exclude candidates below the minimum similarity threshold.
5. Sort candidates by similarity with deterministic tie-breaking.
6. Retain at most `K` inferred neighbors selected by that node.
7. Convert selected connections into a deduplicated undirected union.
8. Preserve explicit catalog relations separately.
9. Apply a global safety cap to the total number of edges.

An undirected union may give a node more than K incident edges when it is selected by other nodes. This is acceptable as long as each node selects no more than K outgoing inferred candidates.

A mutual-kNN mode may optionally be added as a setting for a sparser graph.

### Configuration

Rename or replace ambiguous settings such as `maxNeighborsPerSeed` with a clearer setting:

```json
{
  "islands": {
    "maxInferredNeighborsPerNode": 8,
    "minimumSimilarity": 0.12,
    "maxEdges": 500
  }
}
```

Backward-compatible loading of the previous setting name may be kept temporarily.

### Explicit relations

* Explicit relations must remain visually different from inferred similarity edges.
* Explicit relations must not be removed merely because they are outside a node’s inferred K nearest neighbors.
* A global safety cap may still be applied to prevent unusable graphs.

### Layout

* Edge similarity should influence layout distance.
* Stronger connections should generally appear closer.
* Connected components must be calculated using the edges that are actually displayed.
* Disconnected islands must not be joined through fabricated edges.
* Layout output must remain deterministic for identical graph input.

### Acceptance criteria

* No all-pairs similarity loop is introduced.
* Inferred candidate selection is bounded by an inverted index.
* Each node selects no more than K inferred neighbors.
* Explicit and inferred edges remain distinguishable.
* Unit tests verify edge limits, deterministic ordering, explicit-edge preservation, and disconnected components.

---

## FR-5. Make Evolution Edges Explainable

### Requirement

Evolution branches must show why two works are connected.

The current node-level browser tooltip is not sufficient. The explanation must be attached to the edge itself.

### Edge information

Each Evolution edge must retain:

* Similarity score
* Number of shared features
* Top contributing concepts or tags
* Contribution strength
* Feature origin:

  * Direct work concept
  * Related person or organization
  * Content or parental guide
  * Explicit relationship, when relevant

Suggested structure:

```ts
interface EdgeEvidence {
  score: number;
  sharedFeatureCount: number;
  topFactors: Array<{
    id: string;
    label: string;
    contribution: number;
    source: "direct" | "contributor" | "organization" | "content-guide";
  }>;
}
```

### UI behavior

At minimum, hovering or focusing an edge must display:

* Direction: earlier work → later work
* Similarity score
* Shared feature count
* Top one to three explanatory factors

Example:

```text
Similarity: 0.64
Shared factors:
• Cyberpunk — direct concept
• Ridley Scott — director-derived feature
• Violence: high — content-guide similarity
```

### Display rules

* A compact label containing the strongest factor may be displayed directly on the edge.
* Full details may be placed in a tooltip or popover.
* Labels may be hidden at low zoom levels to reduce visual noise.
* Tooltips must work by keyboard focus, not only mouse hover.
* Do not rely solely on the native HTML `title` attribute.
* Arrows must clearly point from the earlier work to the later work.

### Acceptance criteria

* Every inferred Evolution edge has evidence metadata.
* The user can inspect the evidence from the graph.
* Edge explanations use human-readable labels rather than numeric IDs.
* Hover and keyboard focus are both tested.

---

## FR-6. Build One Mixed Chronological Evolution Structure

### Requirement

Evolution must present one mixed chronological structure containing all supported work families.

It must not create a separate visual tree for every type, genre, or small cluster.

### Structural rules

1. Works of different families may belong to the same Evolution structure.
2. A work may have zero or one inferred parent.
3. A parent must be strictly earlier than its child.
4. Cycles are forbidden.
5. Parent selection must be deterministic.
6. Work kind may affect ranking through a configurable preference, but it must not act as an absolute partition.
7. People, groups, companies, and other contributor entities must not appear as Evolution nodes.
8. Related entities may influence work similarity indirectly through derived features.
9. Undated works may remain roots or appear in a separate undated section.
10. Unrelated works must not be connected only to force a single root.

### Tree versus forest

The preferred visual result is a large mixed branching chronology.

However, a forest is valid when the available data does not provide sufficiently strong evidence to connect all works.

The implementation must prefer meaningful roots over fabricated relationships.

Do not reduce similarity thresholds solely to produce one connected tree.

### Layout

* Chronology must be visually clear.
* Earlier works should appear to the left and later works to the right.
* Multiple roots must share one canvas and one chronological coordinate system.
* Small root trees may be visually grouped, but they must not be rendered as unrelated miniature canvases.
* Existing expand, collapse, grouping, search, and reveal behavior must continue to work.

### Improving connectivity

Reduce unnecessary small trees by improving:

* Feature coverage
* Contributor-derived features
* Content-guide features
* Candidate generation
* Polarity handling
* Relation-type weighting

Do not improve connectivity by inventing unsupported edges.

### Acceptance criteria

* The graph contains work entities only.
* All work families use the same parent-selection process.
* All edges point forward in time.
* The graph has no cycles.
* Multiple roots are rendered together.
* Sparse data produces a forest rather than fake low-confidence connections.

---

## FR-7. Use Tag Weight and Polarity Consistently

### Requirement

Tag or concept weight and polarity must affect:

* Relevance sorting
* Recommendations
* Islands similarity
* Evolution parent selection
* Evolution grouping
* Graph explanations

Date, title, and type sorting must remain literal and must not be modified by relevance scoring.

### Canonical feature representation

Introduce one documented feature-vector specification.

A suitable baseline is:

```text
normalized magnitude = clamp(weight / 100, 0, 1)

polarity sign:
- polarity < 0  → -1
- polarity = 0  → +1 for legacy/default positive presence
- polarity > 0  → +1

base feature value =
normalized magnitude × polarity sign

final feature value =
base feature value × IDF × source multiplier
```

The exact formula may be adjusted, but the same semantics must be used across the Python and TypeScript implementations.

### Similarity

Use a polarity-aware similarity calculation.

Expected behavior:

* High-weight matching features contribute more than low-weight features.
* Opposite-polarity features reduce compatibility or similarity.
* Generic features are downweighted through IDF or an equivalent mechanism.
* A negative final similarity must never create an inferred graph edge.
* The strongest individual contributions must remain available for explanations.

### Relevance sorting

When sorting by relevance:

* Positive, high-weight matches should rank first.
* Explicit negative associations must not be treated as ordinary positive matches.
* Search and selected-concept relevance should use the same feature semantics.
* Explicit Date, Label, and Kind sorts must remain deterministic literal sorts.

### Recommendation scoring

Recommendations must:

* Build a user preference profile from liked works.
* Subtract evidence from disliked works.
* Use candidate feature weights and polarity.
* Use direct and inherited feature multipliers.
* Exclude already rated works.
* Require positive recommendation evidence.
* Retain positive and negative score contributions for explanation.

### Cross-language consistency

Evolution is generated in Python while Recommendations and Islands currently run in TypeScript.

Create shared golden fixtures that verify that Python and TypeScript interpret:

* Weight
* Polarity
* IDF
* Source multipliers
* Similarity

in the same way.

### Acceptance criteria

Unit tests must demonstrate that:

* Raising a matching feature weight raises its relevance.
* Opposite polarity decreases compatibility.
* Polarity is no longer silently ignored.
* Generic concepts contribute less than rare, specific concepts.
* Python and TypeScript produce compatible scores for shared fixtures.

---

## FR-8. Include Related People, Groups, and Organizations as Indirect Features

### Requirement

Recommendations and similarity must consider relevant metadata from related entities, including:

* Creators
* Authors
* Directors
* Actors and performers
* Artists
* Composers
* Producers
* Production groups
* Bands and other groups
* Companies and studios
* Publishers
* Other meaningful contributor roles

Parental/content guide data must also be available as an indirect feature source.

### Propagation rules

1. Only direct work concepts receive the full direct-feature weight.
2. Features inherited from related entities must use lower configurable multipliers.
3. Different relation roles may use different multipliers.
4. Feature inheritance must be limited to one relation hop by default.
5. Recursive propagation through contributor networks is not allowed.
6. High-degree entities must not dominate the complete recommendation space.
7. IDF, relation multipliers, and optional per-source caps must be used to control dominant contributors.
8. Feature provenance must be retained for explanations.

Example settings:

```json
{
  "features": {
    "directConceptMultiplier": 1.0,
    "creatorMultiplier": 0.55,
    "directorMultiplier": 0.50,
    "authorMultiplier": 0.55,
    "producerMultiplier": 0.30,
    "performerMultiplier": 0.25,
    "organizationMultiplier": 0.20,
    "contentGuideMultiplier": 0.25
  }
}
```

The exact defaults should be tuned using the real data.

### Evolution restriction

People, groups, and organizations must never become direct Evolution nodes or parents.

They may only affect the feature vectors of work entities.

For example, two films may become more similar because they share a director, but the director must not appear between the films as an Evolution node.

### Explanation examples

Recommendation and graph explanations should be able to say:

* “Shared genre: psychological thriller”
* “Same director: David Lynch”
* “Related through producer: …”
* “Similar content advisory profile”
* “Shared production company”

### Acceptance criteria

* Related entity metadata affects recommendations and similarity with lower weights than direct work concepts.
* Related entities do not appear as Evolution work nodes.
* Feature propagation is one-hop and deterministic.
* Explanations identify whether evidence is direct or inherited.

---

## FR-9. Expand Work Detail Cards

### Requirement

Work cards or detail windows must show the migrated domain data instead of only a date, kind, flat tag list, and external references.

### Required sections

#### Overview

* Title
* Description, when available
* Work family/type
* Release or publication date
* Image
* User rating controls

#### Contributors

Group people and organizations by role, for example:

* Director
* Creator
* Author
* Cast
* Performer
* Composer
* Producer
* Production company
* Publisher
* Group or band

Show names in a compact form. Related entities should be clickable when sufficient entity data is available.

#### Duration and measurements

Show relevant measurements, including:

* Runtime or duration
* Page count
* Track count
* Dimensions or other domain-specific values

Duration must be formatted for humans, for example:

```text
2 h 17 min
```

#### Parental and content guide

Show available:

* Age rating or certificate
* Rating system
* Minimum age
* Content advisory categories
* Advisory severity or score
* Restrictions
* Region or country
* Edition-specific information

Do not display raw JSON.

#### Concepts and tags

Do not show one unstructured tag list.

Split concepts into meaningful categories such as:

* Genres
* Themes
* Keywords
* Styles
* Moods
* Settings
* Subjects
* Technical characteristics
* Other

Use the V2 concept category where available.

Unknown categories must be placed under a safe “Other” section rather than dropped.

Within each section:

* Sort by effective weight and then label.
* Display negative polarity clearly.
* Support collapsed and expanded states.
* Avoid rendering hundreds of concepts immediately.

#### External references

Continue showing external references and identifiers with human-readable names.

### Responsive behavior

* Desktop may continue using floating detail windows.
* On narrow screens, use a full-width modal, sheet, or drawer.
* The user must not need to drag a window on mobile.
* Long sections must remain scrollable.
* The close action must be obvious and keyboard accessible.

### Acceptance criteria

* People and organizations are shown by role.
* Duration is shown when available.
* Age ratings and advisories are shown when available.
* Concepts are grouped by category.
* Missing sections are omitted cleanly.
* No raw internal IDs or raw JSON are exposed to the user.

---

## FR-10. Improve General UI and UX

### Requirement

Improve UI consistency and usability across all four primary views.

### Required improvements

#### Navigation and state

* Preserve filters, sorting, pagination, and relevant graph state when switching views.
* Make the active view visually clear.
* Avoid unexpected scroll resets.
* Use consistent button and input styles.

#### Browse

* Use a sticky or clearly visible filter toolbar.
* Make active filters easy to identify.
* Add a clear-all action.
* Improve mobile filter layout.
* Show result count and page information together.

#### Recommendations

* Show a compact score explanation.
* Distinguish positive and negative evidence.
* Allow recommendation rows to open the enhanced work card.
* Provide a useful empty state when there are too few ratings.

#### Evolution

* Improve edge visibility and arrow direction.
* Add edge tooltips or labels.
* Keep search, fit, reset, and expand controls easy to find.
* Explain that Evolution represents inferred similarity rather than proven historical influence.

#### Islands

* Keep the liked, disliked, recommended, explicit relation, and inferred relation legend.
* Show KNN and threshold information in help text or settings.
* Improve focusing on an individual island.
* Make similarity explanations accessible from nodes or edges.

#### Loading and error states

* Use view-specific loading indicators where practical.
* Display actionable data-loading errors.
* Distinguish missing optional data from a complete application failure.
* Avoid showing an indefinitely blank graph.

#### Accessibility

* Support keyboard navigation.
* Maintain visible focus states.
* Provide accessible labels for icon-only controls.
* Do not encode meaning through color alone.
* Ensure graph tooltips are available by keyboard focus.
* Respect reduced-motion preferences where animation is used.

#### Visual responsiveness

Support at minimum:

* Desktop
* Tablet
* Narrow mobile layouts

Tables may use horizontal scrolling where unavoidable, but primary actions must remain visible.

---

# 4. Shared Feature and Scoring Architecture

## Requirement

Do not maintain unrelated scoring implementations for Recommendations, Evolution, and Islands.

Introduce a shared conceptual scoring specification.

A practical architecture is:

```text
Raw V2 exports
    ↓
Normalized domain model
    ↓
Feature extraction with provenance
    ↓
Weighted feature index
    ├── Browse relevance
    ├── Recommendations
    ├── Islands
    └── Evolution export
```

### Feature provenance

Every derived feature should retain enough information to explain where it came from:

```ts
interface WeightedFeature {
  key: string;
  label: string;
  value: number;
  source:
    | "direct-concept"
    | "creator"
    | "performer"
    | "producer"
    | "organization"
    | "content-guide";
  sourceEntityId?: number;
  relationType?: string;
}
```

### Duplication between Python and TypeScript

It is acceptable to implement equivalent feature extraction in Python and TypeScript when required by build-time and client-side execution.

However:

* The semantics must be documented once.
* Both implementations must use the same settings.
* Both implementations must share golden test fixtures.
* Unexplained score differences are not acceptable.

---

# 5. Performance Requirements

1. Do not render thousands of table rows simultaneously.
2. Do not perform all-pairs work similarity calculations in the browser.
3. Build reusable inverted indexes once per loaded catalog.
4. Memoize normalized work models and feature vectors.
5. Debounce expensive search operations.
6. Keep graph size bounded through configurable node and edge limits.
7. Avoid recomputing all normalized data when only a local rating changes.
8. Keep deterministic outputs for identical data and settings.
9. Use lazy rendering for long concept and contributor sections.
10. Measure the cost of loading legacy and V2 exports simultaneously and remove redundant payloads after migration completion.

---

# 6. Configuration

Extend `data/settings.json` to contain all user-independent tuning values.

Suggested structure:

```json
{
  "recommendation": {
    "likeWeight": 1.0,
    "dislikeWeight": 1.5,
    "limit": 100
  },
  "features": {
    "directConceptMultiplier": 1.0,
    "creatorMultiplier": 0.55,
    "directorMultiplier": 0.5,
    "authorMultiplier": 0.55,
    "producerMultiplier": 0.3,
    "performerMultiplier": 0.25,
    "organizationMultiplier": 0.2,
    "contentGuideMultiplier": 0.25
  },
  "evolution": {
    "visibleChildrenPerNode": 4,
    "maxInitialRoots": 20,
    "groupingSimilarity": 0.25,
    "minimumSimilarity": 0.18,
    "minimumSharedFeatures": 2
  },
  "islands": {
    "maxRecommendationNodes": 150,
    "maxInferredNeighborsPerNode": 8,
    "maxEdges": 500,
    "minimumSimilarity": 0.12
  },
  "browse": {
    "defaultPageSize": 50,
    "pageSizeOptions": [25, 50, 100]
  }
}
```

All settings must be validated and merged with safe defaults.

---

# 7. Testing Requirements

## Python tests

Add or update tests for:

* V2 export completeness
* Relation and contributor export
* Concept categories
* Measurements and duration
* Advisories and age ratings
* Weighted and polarity-aware feature extraction
* Evolution chronology
* Evolution cycle prevention
* Evolution deterministic parent selection
* Evolution evidence export
* Database validation

## TypeScript unit tests

Add or update tests for:

* V2 normalization
* Concept grouping
* Contributor grouping
* Duration formatting
* Weight normalization
* Polarity handling
* Recommendation scoring
* Recommendation explanation
* KNN edge limits
* Explicit-edge preservation
* Connected components
* Evolution edge explanation data
* Pagination helpers
* Settings migration and validation

## Shared golden fixtures

Create small fixtures covering:

* Positive polarity
* Negative polarity
* Different weights
* Common and rare concepts
* Shared contributor
* Conflicting contributor evidence
* Content-guide similarity
* Cross-family works
* Dated and undated works

Python and TypeScript should produce compatible feature and similarity results for these fixtures.

## E2E tests

Cover at minimum:

1. Browse pagination
2. Filtering resets pagination
3. Changing page size
4. Opening an enhanced work card
5. Displaying contributors
6. Displaying duration
7. Displaying content-guide information
8. Recommendation explanation
9. Evolution edge tooltip
10. Evolution search and reveal
11. Islands rendering with bounded edges
12. Narrow-screen detail presentation

## Required validation commands

```sh
.venv/bin/python -m pytest tests -q
npm run typecheck
npm run test:unit
npm run build
npm run test:e2e
```

---

# 8. Definition of Done

The task is complete when:

* Work starts from the `migration` branch.
* The frontend uses the V2 domain model as its primary data source.
* Legacy data dependencies are removed or isolated behind a documented compatibility adapter.
* Catalog tables are paginated.
* Tag and concept weights affect relevance and recommendations.
* Polarity is handled consistently and is covered by tests.
* Related people and organizations influence recommendations and similarity indirectly.
* Related entities do not become Evolution nodes.
* Evolution shows one mixed chronological canvas with valid forest fallback.
* Evolution edges expose human-readable explanations.
* Islands use bounded up-to-K inferred neighbors.
* Work cards show contributors, duration, content guide data, and categorized concepts.
* SQLite storage through Git or Git LFS has a documented decision.
* CI can retrieve and validate the database.
* All tests, type checking, exports, and production builds pass.
* README and developer documentation are updated.
* No new mandatory backend service is introduced.

---

# 9. Non-Goals

The following are explicitly outside the scope:

* Claiming that Evolution edges prove real historical influence
* Forcing all works into one connected tree
* Adding people or companies as direct Evolution nodes
* Introducing a mandatory server-side API
* Rendering every possible graph edge
* Performing all-pairs browser similarity calculations
* Displaying raw database or JSON structures in the UI
* Rewriting the entire Git history without explicit approval

---

# 10. Suggested Implementation Order

## Phase 1: Domain migration

1. Create normalized V2 frontend models.
2. Migrate work cards.
3. Migrate Browse.
4. Remove duplicated legacy data access where possible.

## Phase 2: Shared feature model

1. Implement weight and polarity semantics.
2. Add contributor-derived and content-guide features.
3. Add shared fixtures and cross-language tests.

## Phase 3: Recommendations and sorting

1. Migrate recommendation scoring.
2. Add relevance sorting.
3. Add detailed recommendation explanations.

## Phase 4: Graphs

1. Update Islands to the shared feature model.
2. Verify and test bounded k-NN behavior.
3. Update Evolution export and parent scoring.
4. Add edge evidence and tooltips.
5. Improve the unified chronological layout.

## Phase 5: Performance and UI polish

1. Add pagination.
2. Improve responsive behavior.
3. Improve loading, error, and empty states.
4. Perform an accessibility review.
5. Remove obsolete migration compatibility code.

## Phase 6: Database storage and documentation

1. Complete the Git/LFS decision.
2. Configure LFS and CI when selected.
3. Update setup, export, testing, and deployment documentation.
