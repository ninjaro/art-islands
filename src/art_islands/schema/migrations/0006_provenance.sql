pragma foreign_keys = on;

create table if not exists entity_facts (
    entity_fact_id   integer primary key,
    entity_id        integer not null references entities(entity_id) on delete cascade,
    property_code    text not null,
    value_type       text not null,
    value_text       text,
    value_number     real,
    value_entity_id  integer references entities(entity_id),
    value_date       text,
    date_precision   integer,
    unit             text,
    qualifiers_json  text,
    rank             text,
    source_record_id integer references source_records(source_record_id),
    check (date_precision is null or date_precision between 0 and 3)
);

create index if not exists source_records_source_idx
on source_records(data_source_id, external_id);

create index if not exists entity_facts_entity_idx
on entity_facts(entity_id, property_code);
