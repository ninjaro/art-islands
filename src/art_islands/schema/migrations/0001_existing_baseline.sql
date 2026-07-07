pragma foreign_keys = on;

create table if not exists entities (
    entity_id       integer primary key,
    label           text not null,
    entity_kind     integer not null default 0,
    release_date    text,
    date_precision  integer not null default 0,
    is_catalogued   integer not null default 0,
    image_ref       text,

    check (entity_kind between 0 and 255),
    check (date_precision between 0 and 3),
    check (is_catalogued in (0, 1))
);

create table if not exists entity_refs (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    ref_kind   integer not null,
    ref_value  text not null,

    primary key (entity_id, ref_kind),
    unique (ref_kind, ref_value),
    check (ref_kind between 0 and 255)
);

create table if not exists tags (
    tag_id       integer primary key,
    name         text not null unique,
    description  text,
    tag_kind     integer not null default 0,
    namespace    text,
    value        text,

    check (tag_kind between 0 and 255)
);

create table if not exists entity_tags (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    tag_id     integer not null references tags(tag_id) on delete cascade,
    weight     integer not null default 50,
    polarity   integer not null default 0,

    primary key (entity_id, tag_id),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
);

create table if not exists entity_links (
    source_entity_id  integer not null references entities(entity_id) on delete cascade,
    target_entity_id  integer not null references entities(entity_id) on delete cascade,
    link_kind         integer not null default 0,
    weight            integer not null default 25,
    polarity          integer not null default 0,
    legacy_tag_id     integer references tags(tag_id) on delete set null,

    primary key (source_entity_id, target_entity_id, link_kind),
    check (link_kind between 0 and 255),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
);

create table if not exists entity_tag_refs (
    entity_id  integer not null,
    tag_id     integer not null,
    ref_id     integer not null,

    primary key (entity_id, tag_id, ref_id),
    foreign key (entity_id, tag_id)
        references entity_tags(entity_id, tag_id)
        on delete cascade
);

create table if not exists entity_link_refs (
    source_entity_id  integer not null,
    target_entity_id  integer not null,
    link_kind         integer not null,
    ref_id            integer not null,

    primary key (source_entity_id, target_entity_id, link_kind, ref_id),
    foreign key (source_entity_id, target_entity_id, link_kind)
        references entity_links(source_entity_id, target_entity_id, link_kind)
        on delete cascade
);

create index if not exists entities_catalog_date_idx
on entities(is_catalogued, release_date, label);

create index if not exists entity_tags_tag_idx
on entity_tags(tag_id, entity_id);

create index if not exists entity_links_target_idx
on entity_links(target_entity_id, source_entity_id);
