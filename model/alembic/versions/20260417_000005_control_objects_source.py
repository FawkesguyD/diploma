from __future__ import annotations

from alembic import op


revision = "20260417_000005"
down_revision = "20260417_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
          area numeric(12, 2) not null,
          rooms integer,
          kitchen_area numeric(12, 2),
          level integer,
          levels integer,
          building_type varchar(255),
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
        )
        """
    )
    op.execute(
        """
        create index if not exists ix_analytics_control_objects_seed_rank
          on analytics_control_objects (sample_seed, sample_rank)
        """
    )
    op.execute(
        """
        create index if not exists ix_analytics_control_objects_listing_id
          on analytics_control_objects (listing_id)
        """
    )
    op.execute("alter table normalized_listings add column if not exists source_object_id text")
    op.execute(
        """
        update normalized_listings
        set source_object_id = 'raw:' || raw_listing_id::text
        where source_object_id is null
          and raw_listing_id is not null
        """
    )
    op.execute(
        """
        do $$
        begin
          if exists (
            select 1
            from information_schema.table_constraints
            where table_schema = current_schema()
              and table_name = 'normalized_listings'
              and constraint_name = 'normalized_listings_raw_listing_id_fkey'
          ) then
            alter table normalized_listings drop constraint normalized_listings_raw_listing_id_fkey;
          end if;
        end $$;
        """
    )
    op.execute("drop index if exists ix_normalized_listings_raw_listing_id")
    op.execute("create index if not exists ix_normalized_listings_raw_listing_id on normalized_listings (raw_listing_id)")
    op.execute(
        """
        create unique index if not exists ix_normalized_listings_source_object_id
          on normalized_listings (source_object_id)
        """
    )
    op.execute("alter table normalized_listings alter column raw_listing_id drop not null")
    op.execute(
        """
        insert into analytics_control_objects (
          source_object_id,
          normalized_listing_id,
          raw_listing_id,
          listing_id,
          listing_price,
          listing_currency,
          target_proxy_price,
          target_source,
          area,
          rooms,
          kitchen_area,
          level,
          levels,
          building_type,
          object_type,
          region,
          latitude,
          longitude,
          source_url,
          source_payload,
          sample_seed,
          sample_rank
        )
        select
          coalesce(nl.source_object_id, 'listing:' || l.id::text) as source_object_id,
          nl.id as normalized_listing_id,
          nl.raw_listing_id,
          l.id as listing_id,
          l.listing_price,
          coalesce(l.listing_currency, 'RUB') as listing_currency,
          l.listing_price as target_proxy_price,
          'listing_price_proxy' as target_source,
          l.area,
          l.rooms,
          l.kitchen_area_m2 as kitchen_area,
          l.floor as level,
          l.total_floors as levels,
          l.building_type,
          nl.normalized_payload ->> 'object_type' as object_type,
          coalesce(nl.normalized_payload ->> 'region', l.city, l.district) as region,
          l.latitude,
          l.longitude,
          l.source_url,
          jsonb_strip_nulls(
            jsonb_build_object(
              'listing_id', l.id,
              'title', l.title,
              'city', l.city,
              'district', l.district,
              'condition', l.condition,
              'seller_type', l.seller_type,
              'year_built', l.year_built
            )
          ) as source_payload,
          42 as sample_seed,
          row_number() over (order by l.id) as sample_rank
        from listings l
        left join lateral (
          select *
          from normalized_listings nl_inner
          where nl_inner.listing_id = l.id
          order by nl_inner.id
          limit 1
        ) nl on true
        where l.listing_price is not null
          and l.area is not null
        on conflict (sample_seed, source_object_id) do nothing
        """
    )
    op.execute("drop table if exists raw_listings cascade")


def downgrade() -> None:
    op.execute(
        """
        create table if not exists raw_listings (
          id bigserial primary key,
          source_name varchar(255) not null,
          external_id varchar(255) not null,
          raw_payload json not null,
          ingested_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        """
        create unique index if not exists ix_raw_listings_source_external
          on raw_listings (source_name, external_id)
        """
    )
    op.execute(
        """
        insert into raw_listings (id, source_name, external_id, raw_payload)
        select distinct raw_listing_id, 'legacy', raw_listing_id::text, '{}'::json
        from normalized_listings
        where raw_listing_id is not null
        on conflict do nothing
        """
    )
    op.execute("delete from normalized_listings where raw_listing_id is null")
    op.execute("drop index if exists ix_normalized_listings_source_object_id")
    op.execute("drop index if exists ix_normalized_listings_raw_listing_id")
    op.execute("alter table normalized_listings drop column if exists source_object_id")
    op.execute("alter table normalized_listings alter column raw_listing_id set not null")
    op.execute(
        """
        alter table normalized_listings
        add constraint normalized_listings_raw_listing_id_fkey
        foreign key (raw_listing_id) references raw_listings(id) on delete cascade
        """
    )
    op.execute(
        """
        create unique index if not exists ix_normalized_listings_raw_listing_id
          on normalized_listings (raw_listing_id)
        """
    )
    op.execute("drop table if exists analytics_control_objects")
