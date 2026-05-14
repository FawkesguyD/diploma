from __future__ import annotations

from alembic import op


revision = "20260419_000006"
down_revision = "20260417_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table analytics_control_objects add column if not exists title varchar(500)")
    op.execute("alter table analytics_control_objects add column if not exists city varchar(255)")
    op.execute("alter table analytics_control_objects add column if not exists district varchar(255)")
    op.execute("alter table analytics_control_objects add column if not exists floor integer")
    op.execute("alter table analytics_control_objects add column if not exists total_floors integer")
    op.execute("alter table analytics_control_objects add column if not exists condition varchar(255)")
    op.execute("alter table analytics_control_objects add column if not exists year_built integer")
    op.execute("alter table analytics_control_objects add column if not exists seller_type varchar(255)")
    op.execute(
        """
        update analytics_control_objects
        set
          title = coalesce(title, nullif(source_payload ->> 'title', '')),
          city = coalesce(city, nullif(source_payload ->> 'city', '')),
          district = coalesce(district, nullif(source_payload ->> 'district', '')),
          floor = coalesce(floor, level),
          total_floors = coalesce(total_floors, levels),
          condition = coalesce(condition, nullif(source_payload ->> 'condition', '')),
          seller_type = coalesce(seller_type, nullif(source_payload ->> 'seller_type', '')),
          year_built = coalesce(
            year_built,
            case
              when nullif(source_payload ->> 'year_built', '') ~ '^-?[0-9]+(\\.[0-9]+)?$'
              then (source_payload ->> 'year_built')::numeric::integer
              else null
            end
          )
        """
    )


def downgrade() -> None:
    op.execute("alter table analytics_control_objects drop column if exists seller_type")
    op.execute("alter table analytics_control_objects drop column if exists year_built")
    op.execute("alter table analytics_control_objects drop column if exists condition")
    op.execute("alter table analytics_control_objects drop column if exists total_floors")
    op.execute("alter table analytics_control_objects drop column if exists floor")
    op.execute("alter table analytics_control_objects drop column if exists district")
    op.execute("alter table analytics_control_objects drop column if exists city")
    op.execute("alter table analytics_control_objects drop column if exists title")
