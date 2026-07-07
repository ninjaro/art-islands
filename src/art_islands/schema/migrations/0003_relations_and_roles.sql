pragma foreign_keys = on;

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
    source_record_id      integer references source_records(source_record_id),
    unique (identifier_scheme_id, value),
    check (is_primary in (0, 1))
);

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
    role_label         text,
    character_label    text,
    ordering           integer,
    weight             integer not null default 50,
    confidence         real,
    polarity           integer not null default 0,
    start_date_id      integer,
    end_date_id        integer,
    is_manual          integer not null default 0,
    source_record_id   integer references source_records(source_record_id),
    unique (
        source_entity_id,
        target_entity_id,
        relation_type_id,
        role_label,
        character_label
    ),
    check (weight between 0 and 100),
    check (polarity between -1 and 1),
    check (is_manual in (0, 1))
);

create index if not exists entity_identifiers_entity_idx
on entity_identifiers(entity_id, identifier_scheme_id);

create index if not exists entity_relations_source_idx
on entity_relations(source_entity_id, relation_type_id);

create index if not exists entity_relations_target_idx
on entity_relations(target_entity_id, relation_type_id);

create view if not exists v_entity_refs_compat as
select
    entity_id,
    identifier_scheme_id as ref_kind,
    value as ref_value
from entity_identifiers;
