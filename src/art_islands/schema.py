from __future__ import annotations


DOMAIN_SCHEMA = """
pragma journal_mode = delete;
pragma foreign_keys = on;

create table if not exists entities (
    entity_id          integer primary key,
    label              text not null,
    entity_kind        integer not null default 0,
    release_date       text,
    date_precision     integer not null default 0,
    is_catalogued      integer not null default 0,
    image_ref          text,
    short_description  text,
    entity_family      text,
    check (entity_kind between 0 and 255),
    check (date_precision between 0 and 3),
    check (is_catalogued in (0, 1))
);
create index if not exists entities_catalog_date_idx
on entities(is_catalogued, release_date, label);

create table if not exists identifier_schemes (
    identifier_scheme_id integer primary key,
    code                 text not null unique,
    label                text not null,
    entity_family        text,
    value_pattern        text,
    url_template         text
);

create table if not exists entity_identifiers (
    entity_identifier_id  integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    identifier_scheme_id  integer not null references identifier_schemes(identifier_scheme_id),
    value                 text not null,
    is_primary            integer not null default 0,
    unique (identifier_scheme_id, value),
    check (is_primary in (0, 1))
);
create index if not exists entity_identifiers_entity_idx
on entity_identifiers(entity_id, identifier_scheme_id);

create table if not exists entity_type_definitions (
    entity_type_id integer primary key,
    code           text not null unique,
    family         text not null,
    label          text not null,
    description    text
);

create table if not exists entity_types (
    entity_id      integer not null references entities(entity_id) on delete cascade,
    entity_type_id integer not null references entity_type_definitions(entity_type_id),
    is_primary     integer not null default 0,
    confidence     real,
    primary key (entity_id, entity_type_id),
    check (is_primary in (0, 1))
) without rowid;
create index if not exists entity_types_type_idx
on entity_types(entity_type_id, entity_id);

create table if not exists entity_texts (
    entity_text_id integer primary key,
    entity_id      integer not null references entities(entity_id) on delete cascade,
    text_kind      text not null,
    language       text,
    value          text not null,
    is_primary     integer not null default 0,
    check (text_kind in ('label', 'alias', 'description')),
    check (is_primary in (0, 1))
);
create index if not exists entity_texts_entity_kind_idx
on entity_texts(entity_id, text_kind);

create table if not exists relation_types (
    relation_type_id integer primary key,
    code             text not null unique,
    label            text not null,
    category         text not null,
    source_family    text,
    target_family    text,
    inverse_code     text
);

create table if not exists entity_relations (
    entity_relation_id integer primary key,
    source_entity_id   integer not null references entities(entity_id) on delete cascade,
    target_entity_id   integer not null references entities(entity_id) on delete cascade,
    relation_type_id   integer not null references relation_types(relation_type_id),
    weight             integer not null default 50,
    confidence         real,
    unique (source_entity_id, target_entity_id, relation_type_id),
    check (weight between 0 and 100)
);
create index if not exists entity_relations_source_idx
on entity_relations(source_entity_id, relation_type_id);
create index if not exists entity_relations_target_idx
on entity_relations(target_entity_id, relation_type_id);

create table if not exists concept_categories (
    concept_category_id integer primary key,
    code                text not null unique,
    label               text not null
);

create table if not exists concepts (
    concept_id          integer primary key,
    label               text not null,
    description         text,
    concept_category_id integer not null references concept_categories(concept_category_id),
    canonical_entity_id integer references entities(entity_id),
    namespace           text,
    value               text,
    confidence          real,
    unique (concept_category_id, label)
);
create index if not exists concepts_category_idx
on concepts(concept_category_id, label);

create table if not exists entity_concepts (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    concept_id integer not null references concepts(concept_id) on delete cascade,
    weight     integer,
    polarity   integer not null default 0,
    confidence real,
    primary key (entity_id, concept_id),
    check (weight is null or weight between 0 and 100),
    check (polarity between -1 and 1)
) without rowid;
create index if not exists entity_concepts_concept_idx
on entity_concepts(concept_id, entity_id);

create table if not exists source_references (
    reference_id text primary key,
    source_type  text,
    title        text,
    url          text,
    publisher    text,
    locator      text
);
create unique index if not exists source_references_url_locator_idx
on source_references(lower(url), coalesce(locator, ''))
where url is not null and trim(url) <> '';

create table if not exists entity_concept_references (
    entity_id    integer not null,
    concept_id   integer not null,
    reference_id text not null references source_references(reference_id),
    primary key (entity_id, concept_id, reference_id),
    foreign key (entity_id, concept_id)
        references entity_concepts(entity_id, concept_id)
        on delete cascade
) without rowid;

create table if not exists entity_dates (
    entity_date_id integer primary key,
    entity_id      integer not null references entities(entity_id) on delete cascade,
    date_type      text not null,
    date_value     text not null,
    date_precision integer not null,
    rank           text,
    is_primary     integer not null default 0,
    confidence     real,
    check (date_precision between 0 and 3),
    check (is_primary in (0, 1))
);
create index if not exists entity_dates_entity_type_idx
on entity_dates(entity_id, date_type, is_primary);

create table if not exists measurement_types (
    measurement_type_id integer primary key,
    code                text not null unique,
    label               text not null,
    default_unit        text
);

create table if not exists entity_measurements (
    entity_measurement_id integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    measurement_type_id   integer not null references measurement_types(measurement_type_id),
    numeric_value         real,
    unit                  text,
    confidence            real
);
create index if not exists entity_measurements_entity_idx
on entity_measurements(entity_id, measurement_type_id);

create table if not exists content_guide_categories (
    category_code text primary key,
    label         text not null,
    description   text,
    cross_media   integer,
    score_min     integer,
    score_max     integer,
    guide_version text
);

create table if not exists entity_content_guide_dimensions (
    entity_id              integer not null references entities(entity_id) on delete cascade,
    category_code          text not null references content_guide_categories(category_code),
    scale_version          text,
    medium                 text,
    intensity              integer,
    centrality             integer,
    explicitness           integer,
    realism                integer,
    recurrence             integer,
    sensory_impact         integer,
    coercion               integer,
    avoidance_priority     integer,
    narrative_proximity    integer,
    language_dependency    integer,
    guidance_level         text,
    content_role           text,
    stance                 text,
    genre_context          text,
    confidence             real,
    uncertainty            integer,
    description            text,
    dimension_values_json  text,
    context_json           text,
    primary key (entity_id, category_code)
) without rowid;

create table if not exists entity_content_guide_references (
    entity_id     integer not null,
    category_code text not null,
    reference_id  text not null references source_references(reference_id),
    primary key (entity_id, category_code, reference_id),
    foreign key (entity_id, category_code)
        references entity_content_guide_dimensions(entity_id, category_code)
        on delete cascade
) without rowid;

create table if not exists entity_restrictions (
    entity_restriction_id integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    country_code          text,
    region_label          text,
    restriction_type      text not null,
    start_date            text,
    end_date              text,
    reason                text,
    edition_label         text,
    status                text
);

create table if not exists entity_restriction_references (
    entity_restriction_id integer not null references entity_restrictions(entity_restriction_id) on delete cascade,
    reference_id          text not null references source_references(reference_id),
    primary key (entity_restriction_id, reference_id)
) without rowid;
"""
