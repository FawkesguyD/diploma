-- =====================================================================
-- Bootstrap-схема PostgreSQL для дипломного проекта.
--
-- ВАЖНО: это bootstrap, а не миграции. Создаёт схемы core/ops и
-- стартовый набор таблиц из docs/design/databases/postgres.md.
-- TODO: заменить/дополнить через Alembic-миграции (см. model/alembic/).
--       Настоящий sql выполнится один раз при пустом volume postgres.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ops;

-- ---------------------------------------------------------------------
-- core.users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.users (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           text        NOT NULL UNIQUE,
    password_hash   text        NOT NULL,
    display_name    text,
    role            text        NOT NULL DEFAULT 'user',
    is_active       boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- core.sources
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.sources (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    kind               text        NOT NULL,
    name               text        NOT NULL,
    url_or_handle      text        NOT NULL,
    enabled            boolean     NOT NULL DEFAULT true,
    poll_interval_sec  integer     NOT NULL DEFAULT 300,
    config             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    last_polled_at     timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    deleted_at         timestamptz
);

CREATE INDEX IF NOT EXISTS ix_sources_kind_enabled    ON core.sources (kind, enabled);
CREATE INDEX IF NOT EXISTS ix_sources_last_polled_at  ON core.sources (last_polled_at);

-- ---------------------------------------------------------------------
-- core.model_registry
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.model_registry (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task        text        NOT NULL,
    version     text        NOT NULL,
    minio_path  text        NOT NULL,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    is_active   boolean     NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (task, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_model_registry_active_per_task
    ON core.model_registry (task)
    WHERE is_active = true;

-- ---------------------------------------------------------------------
-- core.module_configs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.module_configs (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    module      text        NOT NULL,
    name        text        NOT NULL,
    is_active   boolean     NOT NULL DEFAULT false,
    model_id    uuid        REFERENCES core.model_registry(id) ON DELETE SET NULL,
    params      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (module, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_module_configs_active_per_module
    ON core.module_configs (module)
    WHERE is_active = true;

-- ---------------------------------------------------------------------
-- core.user_subscriptions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.user_subscriptions (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    target_kind  text        NOT NULL,
    target_id    uuid,
    target_ref   text        NOT NULL,
    notify       boolean     NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, target_kind, target_ref)
);

CREATE INDEX IF NOT EXISTS ix_user_subscriptions_target
    ON core.user_subscriptions (target_kind, target_ref);

-- ---------------------------------------------------------------------
-- ops.parser_jobs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.parser_jobs (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         uuid        NOT NULL REFERENCES core.sources(id) ON DELETE CASCADE,
    status            text        NOT NULL,
    started_at        timestamptz,
    finished_at       timestamptz,
    items_collected   integer     NOT NULL DEFAULT 0,
    error             text,
    metadata          jsonb       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_parser_jobs_source_started
    ON ops.parser_jobs (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_parser_jobs_status
    ON ops.parser_jobs (status);

-- ---------------------------------------------------------------------
-- ops.model_runs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.model_runs (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    module             text        NOT NULL,
    model_id           uuid        REFERENCES core.model_registry(id) ON DELETE SET NULL,
    module_config_id   uuid        REFERENCES core.module_configs(id) ON DELETE SET NULL,
    triggered_by       text        NOT NULL,
    status             text        NOT NULL,
    started_at         timestamptz,
    finished_at        timestamptz,
    items_processed    integer     NOT NULL DEFAULT 0,
    result_ref         jsonb,
    error              text
);

CREATE INDEX IF NOT EXISTS ix_model_runs_module_started
    ON ops.model_runs (module, started_at DESC);

-- ---------------------------------------------------------------------
-- core.favorites
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS core.favorites (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    target_kind  text        NOT NULL CHECK (target_kind IN ('message','object')),
    target_ref   text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, target_kind, target_ref)
);
CREATE INDEX IF NOT EXISTS ix_favorites_user_kind ON core.favorites (user_id, target_kind, created_at DESC);
