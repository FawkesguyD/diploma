-- Таблица контрольной выборки для сравнения valuation-подходов.
-- Источник строк: датасет Russia_Real_Estate_2021 через services.data_migrator.russia2021_control.

create table if not exists analytics_control_objects (
  id bigserial primary key,
  source_object_id text not null,
  normalized_listing_id bigint,
  raw_listing_id bigint,
  listing_id bigint,
  listing_price numeric(14, 2) not null,
  listing_currency varchar(3) not null default 'RUB',
  target_proxy_price numeric(14, 2),
  target_source varchar(64) not null default 'listing_price_proxy',
  title varchar(500),
  city varchar(255),
  district varchar(255),
  area numeric(12, 2) not null,
  rooms integer,
  kitchen_area numeric(12, 2),
  level integer,
  levels integer,
  floor integer,
  total_floors integer,
  building_type varchar(255),
  condition varchar(255),
  year_built integer,
  seller_type varchar(255),
  object_type varchar(255),
  region varchar(255),
  latitude numeric(10, 6),
  longitude numeric(10, 6),
  source_url varchar(2048),
  source_payload jsonb not null default '{}'::jsonb,
  sample_seed integer not null,
  sample_rank integer not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_analytics_control_objects_seed_source unique (sample_seed, source_object_id)
);

create index if not exists ix_analytics_control_objects_seed_rank
  on analytics_control_objects (sample_seed, sample_rank);

create index if not exists ix_analytics_control_objects_listing_id
  on analytics_control_objects (listing_id);
