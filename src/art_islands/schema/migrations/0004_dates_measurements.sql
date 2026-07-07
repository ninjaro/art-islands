pragma foreign_keys = on;

create table if not exists entity_dates (
    entity_date_id      integer primary key,
    entity_id           integer not null references entities(entity_id) on delete cascade,
    date_type           text not null,
    date_value          text not null,
    date_precision      integer not null,
    end_date_value      text,
    end_date_precision  integer,
    country_entity_id   integer references entities(entity_id),
    place_entity_id     integer references entities(entity_id),
    edition_label       text,
    rank                text,
    is_primary          integer not null default 0,
    confidence          real,
    source_record_id    integer references source_records(source_record_id),
    check (date_precision between 0 and 3),
    check (end_date_precision is null or end_date_precision between 0 and 3),
    check (is_primary in (0, 1))
);

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
    text_value            text,
    unit                  text,
    qualifier             text,
    confidence            real,
    source_record_id      integer references source_records(source_record_id)
);

create index if not exists entity_dates_entity_type_idx
on entity_dates(entity_id, date_type, is_primary);

create index if not exists entity_measurements_entity_idx
on entity_measurements(entity_id, measurement_type_id);
