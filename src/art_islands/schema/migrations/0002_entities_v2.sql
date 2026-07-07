pragma foreign_keys = on;

alter table entities add column short_description text;
alter table entities add column entity_family text;
alter table entities add column completeness_status text;
alter table entities add column confidence real;
alter table entities add column review_state text;
alter table entities add column canonical_source_record_id integer;
alter table entities add column created_at text;
alter table entities add column updated_at text;

create table if not exists data_sources (
    data_source_id integer primary key,
    code           text not null unique,
    label          text not null,
    source_type    text not null,
    base_url       text
);

create table if not exists source_records (
    source_record_id integer primary key,
    data_source_id   integer not null references data_sources(data_source_id),
    external_id      text,
    local_path       text,
    source_url       text,
    retrieved_at     text,
    payload_hash     text,
    revision_id      text,
    metadata_json    text
);

create table if not exists entity_type_definitions (
    entity_type_id integer primary key,
    code           text not null unique,
    family         text not null,
    label          text not null,
    description    text
);

create table if not exists entity_types (
    entity_id        integer not null references entities(entity_id) on delete cascade,
    entity_type_id   integer not null references entity_type_definitions(entity_type_id),
    is_primary       integer not null default 0,
    confidence       real,
    source_record_id integer references source_records(source_record_id),
    primary key (entity_id, entity_type_id),
    check (is_primary in (0, 1))
);

create table if not exists entity_texts (
    entity_text_id   integer primary key,
    entity_id        integer not null references entities(entity_id) on delete cascade,
    text_kind        text not null,
    language         text,
    value            text not null,
    is_primary       integer not null default 0,
    source_record_id integer references source_records(source_record_id),
    check (text_kind in ('label', 'alias', 'description')),
    check (is_primary in (0, 1))
);

create index if not exists entity_types_type_idx
on entity_types(entity_type_id, entity_id);

create index if not exists entity_texts_entity_kind_idx
on entity_texts(entity_id, text_kind, language);
