# Art Islands Domain Simplification Post-Migration Audit

- Original size: 76,910,592 bytes
- Cleaned size: 46,735,360 bytes
- Size reduction: 30,175,232 bytes
- Quick check: ok
- Foreign-key errors: 0
- Catalog QIDs missing: 0

## Retained Counts

| Table | Rows |
| --- | ---: |
| `concept_categories` | 18 |
| `concepts` | 5,337 |
| `content_guide_categories` | 67 |
| `entities` | 16,659 |
| `entity_concept_references` | 263,883 |
| `entity_concepts` | 86,955 |
| `entity_content_guide_dimensions` | 53,039 |
| `entity_content_guide_references` | 174,866 |
| `entity_dates` | 7,590 |
| `entity_identifiers` | 35,152 |
| `entity_measurements` | 1,876 |
| `entity_relations` | 25,604 |
| `entity_restriction_references` | 2 |
| `entity_restrictions` | 1 |
| `entity_texts` | 27,011 |
| `entity_type_definitions` | 27 |
| `entity_types` | 17,898 |
| `identifier_schemes` | 15 |
| `measurement_types` | 11 |
| `relation_types` | 37 |
| `source_references` | 318 |

## Migration Statistics

- Advisory-only content-guide rows migrated: 76
- Useful advisory descriptions migrated: 76
- Concept reference mappings retained: 263,883
- Content-guide reference mappings retained: 174,866
- Restriction reference mappings retained: 2
- Concept assignments with `NULL` weight after cleanup: 12,086

## Validation

- `PRAGMA quick_check`: ok
- `PRAGMA foreign_key_check`: []
- Logical concept-reference orphans: 0
- Logical content-guide-reference orphans: 0
- Logical restriction-reference orphans: 0
