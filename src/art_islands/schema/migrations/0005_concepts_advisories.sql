pragma foreign_keys = on;

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
    legacy_tag_id       integer unique references tags(tag_id) on delete set null,
    classification_rule text,
    confidence          real,
    review_recommended  integer not null default 0,
    unique (concept_category_id, label),
    check (review_recommended in (0, 1))
);

create table if not exists entity_concepts (
    entity_id        integer not null references entities(entity_id) on delete cascade,
    concept_id       integer not null references concepts(concept_id) on delete cascade,
    weight           integer not null default 50,
    polarity         integer not null default 0,
    confidence       real,
    is_manual        integer not null default 0,
    source_record_id integer references source_records(source_record_id),
    primary key (entity_id, concept_id),
    check (weight between 0 and 100),
    check (polarity between -1 and 1),
    check (is_manual in (0, 1))
);

create table if not exists advisory_categories (
    advisory_category_id integer primary key,
    code                 text not null unique,
    label                text not null,
    parent_id            integer references advisory_categories(advisory_category_id)
);

create table if not exists entity_advisories (
    entity_advisory_id   integer primary key,
    entity_id            integer not null references entities(entity_id) on delete cascade,
    advisory_category_id integer not null references advisory_categories(advisory_category_id),
    concept_id           integer references concepts(concept_id),
    severity             integer,
    confidence           real,
    description          text,
    is_manual            integer not null default 0,
    source_record_id     integer references source_records(source_record_id),
    check (severity is null or severity between 0 and 4),
    check (is_manual in (0, 1))
);

create table if not exists age_rating_systems (
    age_rating_system_id integer primary key,
    code                 text not null unique,
    country_code         text,
    label                text not null
);

create table if not exists entity_age_ratings (
    entity_age_rating_id integer primary key,
    entity_id            integer not null references entities(entity_id) on delete cascade,
    age_rating_system_id integer not null references age_rating_systems(age_rating_system_id),
    certificate          text not null,
    minimum_age          integer,
    edition_label        text,
    descriptors_json     text,
    rating_date          text,
    source_record_id     integer references source_records(source_record_id),
    unique (entity_id, age_rating_system_id, certificate, edition_label)
);

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
    status                text,
    source_record_id      integer references source_records(source_record_id)
);

create index if not exists entity_concepts_concept_idx
on entity_concepts(concept_id, entity_id);

create index if not exists concepts_category_idx
on concepts(concept_category_id, label);
