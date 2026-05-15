import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowRight, Heart, Newspaper, TrendingUp, Sparkles, Inbox } from 'lucide-react';
import { api } from '@/api/client';
import { useFavorites, useMessagesInfinite, useTrendsLatest } from '@/api/hooks';
import { MessageCard } from '@/components/MessageCard';
import { ObjectCard } from '@/components/ObjectCard';
import type { Message, RealEstateObject } from '@/api/types';
import { formatDateTime } from '@/lib/utils';

export function HomePage() {
  const trends = useTrendsLatest();
  const messages = useMessagesInfinite({});
  const favorites = useFavorites();

  const top3Trends = trends.data?.items.slice(0, 3) ?? [];
  const fresh5 = useMemo<Message[]>(
    () => (messages.data?.pages[0]?.items ?? []).slice(0, 5),
    [messages.data]
  );

  const favSlice = (favorites.data ?? []).slice(0, 3);
  const favQueries = useQueries({
    queries: favSlice.map((f) => ({
      queryKey: [f.target_kind, f.target_ref],
      queryFn: async () => {
        const path = f.target_kind === 'message' ? `/messages/${f.target_ref}` : `/objects/${f.target_ref}`;
        return (await api.get<Message | RealEstateObject>(path)).data;
      },
    })),
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Главная</h1>
        <p className="text-sm text-muted-foreground">Обзор информационного потока за последнюю неделю</p>
      </div>

      <section className="space-y-3">
        <SectionHeader
          icon={<TrendingUp className="h-4 w-4 text-primary" />}
          title="Топ трендов недели"
          to="/messages?view=trends"
        />
        {trends.isPending ? (
          <SkeletonGrid n={3} h={28} />
        ) : top3Trends.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="h-8 w-8 text-muted-foreground" />}
            title="Трендов пока нет"
            cta={{ label: 'Перейти на страницу трендов', to: '/messages?view=trends' }}
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-3">
            {top3Trends.map((t) => (
              <Link key={t.slug} to="/messages?view=trends" className="block">
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{t.title}</CardTitle>
                    <CardDescription className="font-mono text-[10px]">#{t.slug}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl font-semibold">{t.mentions}</span>
                      <span className="text-xs text-muted-foreground">упоминаний</span>
                      <DeltaBadge delta={t.delta_pct} />
                    </div>
                    <p className="line-clamp-3 text-sm text-muted-foreground">{t.summary}</p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
        {trends.data && (
          <p className="text-xs text-muted-foreground">
            Обновлено {formatDateTime(trends.data.computed_at)}
          </p>
        )}
      </section>

      <section className="space-y-3">
        <SectionHeader
          icon={<Newspaper className="h-4 w-4 text-primary" />}
          title="Свежие сообщения"
          to="/messages"
        />
        {messages.isPending ? (
          <SkeletonGrid n={3} h={32} />
        ) : fresh5.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-8 w-8 text-muted-foreground" />}
            title="Сообщений пока нет"
            cta={{ label: 'Открыть ленту', to: '/messages' }}
          />
        ) : (
          <div className="space-y-3">
            {fresh5.map((m) => (
              <MessageCard key={m.id} message={m} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <SectionHeader
          icon={<Heart className="h-4 w-4 text-primary" />}
          title="Из вашего избранного"
          to="/home"
          hideCta
        />
        {favorites.isPending ? (
          <SkeletonGrid n={3} h={32} />
        ) : favSlice.length === 0 ? (
          <EmptyState
            icon={<Heart className="h-8 w-8 text-muted-foreground" />}
            title="Избранное пусто"
            description="Нажимайте на сердечко в карточке сообщения или объекта, чтобы сохранить его."
            cta={{ label: 'Открыть ленту', to: '/messages' }}
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-3">
            {favSlice.map((fav, i) => {
              const q = favQueries[i];
              if (q.isPending) return <Skeleton key={fav.id} className="h-32 w-full" />;
              if (!q.data) return null;
              return fav.target_kind === 'message' ? (
                <MessageCard key={fav.id} message={q.data as Message} />
              ) : (
                <ObjectCard key={fav.id} object={q.data as RealEstateObject} />
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  to,
  hideCta,
}: {
  icon: React.ReactNode;
  title: string;
  to: string;
  hideCta?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
        {icon}
        {title}
      </h2>
      {!hideCta && (
        <Button variant="ghost" size="sm" asChild>
          <Link to={to}>
            Все <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      )}
    </div>
  );
}

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta === null || delta === undefined) {
    return <Badge variant="muted">новый</Badge>;
  }
  if (delta > 0) {
    return <Badge variant="success">↑ +{delta.toFixed(0)}%</Badge>;
  }
  if (delta < 0) {
    return <Badge variant="muted">↓ {delta.toFixed(0)}%</Badge>;
  }
  return <Badge variant="outline">±0%</Badge>;
}

function SkeletonGrid({ n, h }: { n: number; h: number }) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} className={`h-${h} w-full`} />
      ))}
    </div>
  );
}

function EmptyState({
  icon,
  title,
  description,
  cta,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  cta?: { label: string; to: string };
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 p-10 text-center">
        {icon}
        <h3 className="font-medium">{title}</h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        {cta && (
          <Button variant="outline" size="sm" asChild className="mt-2">
            <Link to={cta.to}>{cta.label}</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
