# services/frontend — SPA для АИС

React 18 + TypeScript + Vite 5 + TanStack Query v5 + Tailwind v3 + shadcn-style Radix UI + Recharts + Leaflet.

## Разработка

```bash
pnpm install
pnpm dev          # http://localhost:5173 (proxy /api → http://localhost)
pnpm typecheck
pnpm lint
pnpm build        # → dist/
pnpm preview
```

При локальной разработке Vite-dev-сервер проксирует `/api` на `http://localhost` (Traefik в compose).

## Переменные окружения

| Имя | По умолчанию | Назначение |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Базовый URL для всех HTTP-запросов фронтенда. В production-сборке через Traefik фронт и бэкенд живут на одном origin → CORS не нужен. |

См. `.env.example`.

## Архитектура

```
src/
  api/
    client.ts          # axios instance + JWT interceptor + 401 hook
    types.ts           # ручные типы по docs/design/api/openapi.yaml
    hooks.ts           # TanStack Query hooks для всех ресурсов
    useMessageStream.ts# SSE-обёртка для /api/messages/stream
  auth/
    AuthProvider.tsx   # context: user, token, login, register, logout
    ProtectedRoute.tsx # ProtectedRoute + AdminRoute
  components/
    AppLayout.tsx
    MessageCard.tsx, ObjectCard.tsx
    theme-provider.tsx, theme-toggle.tsx
    ui/                # shadcn-style Radix-based примитивы
  pages/
    LoginPage.tsx
    MessagesPage.tsx, MessageDetailPage.tsx
    SourcesPage.tsx
    ObjectsPage.tsx, TopUndervaluedPage.tsx
    DashboardsPage.tsx
    MapPage.tsx
  lib/utils.ts         # cn, formatters
public/
  geo/moscow-districts.geojson  # placeholder GeoJSON (5 районов)
```

### Аутентификация

JWT хранится в `localStorage` под ключом `ais_token`. Axios-interceptor добавляет заголовок `Authorization: Bearer …`. На 401 — токен сбрасывается и роутер уходит на `/login`. На монтировании приложения, если токен есть, валидируется через `GET /api/auth/me`.

### SSE (`/api/messages/stream`)

`EventSource` не умеет добавлять кастомные заголовки. Поскольку запрос идёт same-origin, токен передаётся через `?token=<jwt>` query-параметр (бэкенд `nlp-parser` поддерживает оба способа: header и query; иначе SSE отключается, остальная лента работает через REST). Буфер живых событий — максимум 50, новые — сверху, дедупликация по `id`.

### Карта

GeoJSON Москвы лежит в `public/geo/moscow-districts.geojson`. По умолчанию — placeholder (5 районов: presnenskiy, tverskoy, khamovniki, yakimanka, arbat). Чтобы заменить на полноценный набор районов Москвы, положите полный GeoJSON под тем же путём (поля `properties.slug` и `properties.name` обязательны). Цвет = средняя цена ₽/м² из `/api/dashboards/prices/by-district`.

## Docker

Multi-stage `Dockerfile`: `node:20-alpine` собирает SPA → `nginx:alpine` сервит `dist/`. SPA-fallback `try_files $uri /index.html` настроен в `nginx.conf`.

```bash
docker compose build frontend
docker compose up -d frontend
# http://localhost/ — SPA, http://localhost/api/* — бэкенд (Traefik)
```

Traefik labels:
- `PathPrefix(\`/\`)` с `priority=1`, чтобы более длинные `/api`-маршруты выигрывали приоритет.

## API

Все запросы идут на `/api/*`. Полная сводка — `docs/design/api/openapi.yaml`. Типы продублированы вручную в `src/api/types.ts`.
