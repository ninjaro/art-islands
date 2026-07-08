# Removed And Merged Structures

## Removed Or Merged Tables

- `advisory_categories`: Merged into content_guide_categories.
- `age_rating_systems`: Coarse certificates removed in favor of detailed 100-point content guide.
- `data_sources`: Import-source catalog, not curated citation evidence.
- `entity_advisories`: Merged into entity_content_guide_dimensions.
- `entity_advisory_patch_refs`: Merged into entity_content_guide_references.
- `entity_age_rating_patch_refs`: Reference layer for removed coarse certificate rows.
- `entity_age_ratings`: Coarse certificates removed in favor of detailed 100-point content guide.
- `entity_concept_patch_refs`: Renamed to entity_concept_references.
- `entity_concept_source_refs`: Local import provenance; curated references are retained separately.
- `entity_content_guide_patch_refs`: Renamed to entity_content_guide_references.
- `entity_content_guide_source_refs`: Local import provenance; curated references are retained separately.
- `entity_link_refs`: Reference layer for removed legacy compact links.
- `entity_links`: Legacy compact links; explicit normalized relations are retained in entity_relations.
- `entity_refs`: Legacy compact identifiers superseded by entity_identifiers.
- `entity_restriction_patch_refs`: Renamed to entity_restriction_references.
- `entity_tag_refs`: Legacy import-source mappings; curated references are retained in entity_concept_references.
- `entity_tags`: Legacy V1 assignments superseded by entity_concepts.
- `patch_references`: Renamed to source_references and deduplicated by URL plus locator.
- `source_records`: Import-source records and local-layer provenance, not curated citation evidence.
- `tags`: Legacy V1 tag definitions superseded by concepts.

## Removed Columns From Retained Tables

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

## JSON Field Decisions

- `entity_content_guide_dimensions.dimension_values_json` is retained temporarily because it contains unique detailed 100-point component values not normalized elsewhere.
- `entity_content_guide_dimensions.context_json` is retained after removing duplicated `tagContext` keys; remaining context keys describe current content presentation modes.
