# Art Islands Domain Simplification Pre-Migration Audit

- Database: `/home/yarro/Projects/new/art-islands/data/art-islands.sqlite`
- File size: 76,910,592 bytes
- Integrity: ok
- Foreign-key errors: 0

## Table Inventory

| Table | Rows | Approx bytes | Action |
| --- | ---: | ---: | --- |
| `advisory_categories` | 67 | 4,096 | remove/merge |
| `age_rating_systems` | 2 | 4,096 | remove/merge |
| `concept_categories` | 18 | 4,096 | keep |
| `concepts` | 5,337 | 1,376,256 | keep |
| `content_guide_categories` | 64 | 16,384 | keep |
| `data_sources` | 4 | 4,096 | remove/merge |
| `entities` | 16,659 | 864,256 | keep |
| `entity_advisories` | 53,039 | 5,570,560 | remove/merge |
| `entity_advisory_patch_refs` | 174,866 | 4,993,024 | remove/merge |
| `entity_age_rating_patch_refs` | 3 | 4,096 | remove/merge |
| `entity_age_ratings` | 4 | 4,096 | remove/merge |
| `entity_concept_patch_refs` | 263,883 | 8,273,920 | remove/merge |
| `entity_concept_source_refs` | 116,723 | 1,507,328 | remove/merge |
| `entity_concepts` | 86,955 | 1,908,736 | keep |
| `entity_content_guide_dimensions` | 52,963 | 24,121,344 | keep |
| `entity_content_guide_patch_refs` | 174,784 | 8,802,304 | remove/merge |
| `entity_content_guide_source_refs` | 117,612 | 3,747,840 | remove/merge |
| `entity_dates` | 7,590 | 442,368 | keep |
| `entity_identifiers` | 35,152 | 909,312 | keep |
| `entity_link_refs` | 30 | 4,096 | remove/merge |
| `entity_links` | 20,628 | 315,392 | remove/merge |
| `entity_measurements` | 1,876 | 73,728 | keep |
| `entity_refs` | 20,204 | 372,736 | remove/merge |
| `entity_relations` | 25,604 | 864,256 | keep |
| `entity_restriction_patch_refs` | 2 | 4,096 | remove/merge |
| `entity_restrictions` | 1 | 4,096 | keep |
| `entity_tag_refs` | 134,005 | 1,728,512 | remove/merge |
| `entity_tags` | 84,791 | 1,110,016 | remove/merge |
| `entity_texts` | 27,011 | 1,118,208 | keep |
| `entity_type_definitions` | 27 | 4,096 | keep |
| `entity_types` | 17,898 | 249,856 | keep |
| `identifier_schemes` | 15 | 4,096 | keep |
| `measurement_types` | 11 | 4,096 | keep |
| `patch_references` | 321 | 73,728 | remove/merge |
| `relation_types` | 37 | 4,096 | keep |
| `source_records` | 19,458 | 409,600 | remove/merge |
| `tags` | 5,149 | 1,179,648 | remove/merge |

## Columns Marked For Removal

- `concepts.classification_rule`: rows=5,337; nulls=0; distinct=27. Generation/workflow classification rule.
- `concepts.legacy_tag_id`: rows=5,337; nulls=188; distinct=5,149. Legacy V1 bridge identifier.
- `concepts.review_recommended`: rows=5,337; nulls=0; distinct=2. Review queue flag.
- `entity_concepts.source_record_id`: rows=86,955; nulls=74,869; distinct=1,075. Import-source provenance; curated references are mapped separately.
- `entity_dates.country_entity_id`: rows=7,590; nulls=7,590; distinct=0. Empty in the current database.
- `entity_dates.edition_label`: rows=7,590; nulls=7,590; distinct=0. Empty in the current database.
- `entity_dates.end_date_precision`: rows=7,590; nulls=7,590; distinct=0. Empty in the current database.
- `entity_dates.end_date_value`: rows=7,590; nulls=7,590; distinct=0. Empty in the current database.
- `entity_dates.place_entity_id`: rows=7,590; nulls=7,590; distinct=0. Empty in the current database.
- `entity_dates.source_record_id`: rows=7,590; nulls=0; distinct=2,426. Import-source provenance.
- `entity_identifiers.source_record_id`: rows=35,152; nulls=0; distinct=12,588. Import-source provenance.
- `entity_measurements.qualifier`: rows=1,876; nulls=1,876; distinct=0. Empty in the current database.
- `entity_measurements.source_record_id`: rows=1,876; nulls=0; distinct=1,748. Import-source provenance.
- `entity_measurements.text_value`: rows=1,876; nulls=1,876; distinct=0. Empty in the current database.
- `entity_relations.character_label`: rows=25,604; nulls=25,604; distinct=0. Empty in the current database.
- `entity_relations.ordering`: rows=25,604; nulls=25,604; distinct=0. Empty in the current database.
- `entity_relations.polarity`: rows=25,604; nulls=0; distinct=1. Constant zero in the current database.
- `entity_relations.role_label`: rows=25,604; nulls=25,604; distinct=0. Empty in the current database.
- `entity_relations.source_record_id`: rows=25,604; nulls=0; distinct=3,108. Import-source provenance.
- `entity_texts.source_record_id`: rows=27,011; nulls=0; distinct=4,011. Import-source provenance.
- `entity_types.source_record_id`: rows=17,898; nulls=0; distinct=1,492. Import-source provenance.
