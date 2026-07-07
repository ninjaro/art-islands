# Art Islands Domain-Preserving Cleanup Inventory

This inventory was generated before rebuilding the cleaned database. It classifies every source table and records columns removed from trimmed tables.

| Table | Rows | Approx bytes | Primary key | Foreign keys | Code refs | Action | Domain-data note |
| --- | ---: | ---: | --- | --- | ---: | --- | --- |
| advisory_categories | 67 | 4096 | advisory_category_id | parent_id->advisory_categories.advisory_category_id | 2 | keep | Normalized content advisory category definitions. |
| age_rating_systems | 2 | 4096 | age_rating_system_id | - | 2 | keep | Normalized parental/content rating systems. |
| concept_categories | 18 | 4096 | concept_category_id | - | 5 | keep | Domain concept category definitions. |
| concepts | 5337 | 1490944 | concept_id | legacy_tag_id->tags.tag_id<br>canonical_entity_id->entities.entity_id<br>concept_category_id->concept_categories.concept_category_id | 44 | keep | Domain concepts derived from tags and enrichment. |
| content_guide_categories | 64 | 28672 | category_code | - | 2 | trim | Content-guide categories are domain data; raw JSON and update timestamps are not. |
| data_patch_applications | 407 | 4440064 | patch_id | - | 1 | remove | Patch application history and batch accounting. |
| data_sources | 14 | 4096 | data_source_id | - | 2 | trim | Source catalog definitions used by retained source records; unreferenced patch-archive definitions are removed. |
| entities | 16659 | 2330624 | entity_id | - | 87 | trim | Entity identity/display data is kept; review/import/cache columns are removed. |
| entity_advisories | 53039 | 29982720 | entity_advisory_id | source_record_id->source_records.source_record_id<br>concept_id->concepts.concept_id<br>advisory_category_id->advisory_categories.advisory_category_id<br>entity_id->entities.entity_id | 4 | trim | Human-readable advisories and scores are kept; raw payloads and import links are removed. |
| entity_age_ratings | 4 | 4096 | entity_age_rating_id | source_record_id->source_records.source_record_id<br>age_rating_system_id->age_rating_systems.age_rating_system_id<br>entity_id->entities.entity_id | 4 | trim | Ratings are kept; raw payloads and embedded reference JSON are normalized. |
| entity_concept_patch_metadata | 74869 | 140070912 | entity_id, concept_id | entity_id->entity_concepts.entity_id<br>concept_id->entity_concepts.concept_id<br>source_record_id->source_records.source_record_id | 1 | migrate | Patch metadata is removed after source-reference mappings are extracted. |
| entity_concepts | 86955 | 2670592 | entity_id, concept_id | source_record_id->source_records.source_record_id<br>concept_id->concepts.concept_id<br>entity_id->entities.entity_id | 14 | trim | Concept assignments are kept; source links remain resolvable and curation provenance flags are removed. |
| entity_content_guide_dimensions | 52963 | 132673536 | entity_id, category_code | source_record_id->source_records.source_record_id<br>category_code->content_guide_categories.category_code<br>entity_id->entities.entity_id | 5 | trim | Content-guide scores are kept; raw patch payloads are normalized away. |
| entity_dates | 7590 | 442368 | entity_date_id | source_record_id->source_records.source_record_id<br>place_entity_id->entities.entity_id<br>country_entity_id->entities.entity_id<br>entity_id->entities.entity_id | 4 | keep | Domain dates and source links. |
| entity_facts | 0 | 4096 | entity_fact_id | source_record_id->source_records.source_record_id<br>value_entity_id->entities.entity_id<br>entity_id->entities.entity_id | 0 | remove | Empty staging/fact table in the current database. |
| entity_identifiers | 35152 | 909312 | entity_identifier_id | source_record_id->source_records.source_record_id<br>identifier_scheme_id->identifier_schemes.identifier_scheme_id<br>entity_id->entities.entity_id | 8 | keep | External identifiers and their source links. |
| entity_link_refs | 30 | 4096 | source_entity_id, target_entity_id, link_kind, ref_id | source_entity_id->entity_links.source_entity_id<br>target_entity_id->entity_links.target_entity_id<br>link_kind->entity_links.link_kind | 11 | keep | Legacy relationship-to-source mappings. |
| entity_links | 20628 | 360448 | source_entity_id, target_entity_id, link_kind | legacy_tag_id->tags.tag_id<br>target_entity_id->entities.entity_id<br>source_entity_id->entities.entity_id | 18 | keep | Compact semantic links used by the current app. |
| entity_measurements | 1876 | 73728 | entity_measurement_id | source_record_id->source_records.source_record_id<br>measurement_type_id->measurement_types.measurement_type_id<br>entity_id->entities.entity_id | 5 | keep | Duration, page counts, dimensions, and source links. |
| entity_refs | 20204 | 417792 | entity_id, ref_kind | entity_id->entities.entity_id | 21 | keep | Compact external references used by CLI/export/batches. |
| entity_relations | 25604 | 1015808 | entity_relation_id | source_record_id->source_records.source_record_id<br>relation_type_id->relation_types.relation_type_id<br>target_entity_id->entities.entity_id<br>source_entity_id->entities.entity_id | 9 | trim | Contributor/creator/semantic relationships are kept; manual/import flags are removed. |
| entity_restrictions | 1 | 4096 | entity_restriction_id | source_record_id->source_records.source_record_id<br>entity_id->entities.entity_id | 4 | trim | Restriction facts are kept; raw payloads and embedded reference JSON are normalized. |
| entity_tag_refs | 134005 | 2154496 | entity_id, tag_id, ref_id | entity_id->entity_tags.entity_id<br>tag_id->entity_tags.tag_id | 11 | keep | Legacy tag-to-source mappings. |
| entity_tags | 84791 | 1368064 | entity_id, tag_id | tag_id->tags.tag_id<br>entity_id->entities.entity_id | 32 | keep | Entity tag weights and polarity. |
| entity_texts | 27011 | 1118208 | entity_text_id | source_record_id->source_records.source_record_id<br>entity_id->entities.entity_id | 4 | keep | Labels, aliases, descriptions, and source links. |
| entity_type_definitions | 27 | 4096 | entity_type_id | - | 3 | keep | Entity type definitions. |
| entity_types | 17898 | 286720 | entity_id, entity_type_id | source_record_id->source_records.source_record_id<br>entity_type_id->entity_type_definitions.entity_type_id<br>entity_id->entities.entity_id | 8 | keep | Entity type assignments and source links. |
| identifier_schemes | 15 | 4096 | identifier_scheme_id | - | 5 | keep | External identifier scheme definitions. |
| measurement_types | 11 | 4096 | measurement_type_id | - | 3 | keep | Measurement type definitions. |
| patch_references | 319 | 200704 | reference_id | source_record_id->source_records.source_record_id | 10 | trim | Citation catalog is kept; raw JSON and retrieval/update timestamps are removed. |
| relation_types | 37 | 4096 | relation_type_id | - | 4 | keep | Semantic relationship type definitions. |
| schema_migrations | 6 | 4096 | version | - | 1 | remove | Migration history. |
| source_records | 19865 | 7667712 | source_record_id | data_source_id->data_sources.data_source_id | 16 | trim | Current source identities are kept; file offsets, hashes, timestamps, payload metadata, and unreferenced patch-archive records are removed. |
| tags | 5149 | 1179648 | tag_id | - | 165 | keep | Tag definitions. |

## Value Normalization

- `entity_concepts.source_record_id`: values pointing to `data_patch_archive` source records are set to null because they identify patch application provenance. Real legacy/local-layer source values are retained, and source citations from patch metadata are preserved in `entity_concept_patch_refs` and `entity_concept_source_refs`.
- `source_records` / `data_sources`: `data_patch_archive` records are removed after those patch-provenance pointers are nulled. Retained fact-source mappings continue to resolve to `source_records` or `patch_references`.

## Removed Columns

### `content_guide_categories`
- `raw_json`: serialized copy of category definition; not required to resolve retained foreign keys.
- `updated_at`: database update timestamp; not required to resolve retained foreign keys.

### `entities`
- `canonical_source_record_id`: import provenance pointer; not required to resolve retained foreign keys.
- `completeness_status`: processing/review status; not required to resolve retained foreign keys.
- `confidence`: entity-level enrichment confidence, not displayed or required; not required to resolve retained foreign keys.
- `created_at`: database creation timestamp; not required to resolve retained foreign keys.
- `review_state`: review workflow state; not required to resolve retained foreign keys.
- `updated_at`: database update timestamp; not required to resolve retained foreign keys.

### `entity_advisories`
- `is_manual`: curation provenance flag; not required to resolve retained foreign keys.
- `raw_json`: serialized patch payload; not required to resolve retained foreign keys.
- `reference_ids_json`: embedded source references migrated to entity_advisory_patch_refs; not required to resolve retained foreign keys.
- `source_record_id`: patch/import provenance; source citations are normalized into mapping tables; not required to resolve retained foreign keys.

### `entity_age_ratings`
- `raw_json`: serialized patch payload; not required to resolve retained foreign keys.
- `reference_ids_json`: embedded source references migrated to entity_age_rating_patch_refs; not required to resolve retained foreign keys.
- `source_record_id`: patch/import provenance; source citations are normalized into mapping tables; not required to resolve retained foreign keys.

### `entity_concept_patch_metadata`
- `*`: patch/evidence history table removed after reference mappings are extracted; not required to resolve retained foreign keys.

### `entity_concepts`
- `is_manual`: curation provenance flag; not required to resolve retained foreign keys.

### `entity_content_guide_dimensions`
- `context_flags_json`: pipeline context flags; meaningful context is kept in context_json; not required to resolve retained foreign keys.
- `entity_references_json`: duplicates entity external identifiers; not required to resolve retained foreign keys.
- `evidence_json`: serialized evidence labels/modes duplicated from normalized tags and raw payloads; not required to resolve retained foreign keys.
- `raw_json`: serialized patch payload; unique numeric ratings are migrated to dimension_values_json; not required to resolve retained foreign keys.
- `reference_ids_json`: embedded source references migrated to entity_content_guide_patch_refs; not required to resolve retained foreign keys.
- `source_basis`: mining/editorial rationale rather than a rating value; not required to resolve retained foreign keys.
- `source_record_id`: patch/import provenance; source citations are normalized into mapping tables; not required to resolve retained foreign keys.
- `updated_at`: database update timestamp; not required to resolve retained foreign keys.

### `entity_relations`
- `is_manual`: curation provenance flag; not required to resolve retained foreign keys.

### `entity_restrictions`
- `raw_json`: serialized patch payload; not required to resolve retained foreign keys.
- `reference_ids_json`: embedded source references migrated to entity_restriction_patch_refs; not required to resolve retained foreign keys.
- `source_record_id`: patch/import provenance; source citations are normalized into mapping tables; not required to resolve retained foreign keys.

### `patch_references`
- `raw_json`: serialized citation row; not required to resolve retained foreign keys.
- `retrieved_at`: retrieval timestamp, not source publication date; not required to resolve retained foreign keys.
- `source_record_id`: patch/import provenance pointer; not required to resolve retained foreign keys.
- `updated_at`: database update timestamp; not required to resolve retained foreign keys.

### `source_records`
- `local_path`: source file path used during mining/import; not required to resolve retained foreign keys.
- `metadata_json`: file offsets and staging metadata; not required to resolve retained foreign keys.
- `payload_hash`: raw payload recovery/debug hash; not required to resolve retained foreign keys.
- `retrieved_at`: import/retrieval timestamp; not required to resolve retained foreign keys.
- `revision_id`: import revision metadata; not required to resolve retained foreign keys.
