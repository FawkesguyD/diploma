import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useMessagesInfinite, useRecomputeTrends, useTrendsLatest, type MessageFilters } from '@/api/hooks';
import { useMessageStream } from '@/api/useMessageStream';
import { MessageCard } from '@/components/MessageCard';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Inbox, LoaderCircle, Radio, RefreshCcw, Sparkles, TrendingDown, TrendingUp } from 'lucide-react';
import { extractErrorMessage } from '@/api/client';
import { formatDateTime } from '@/lib/utils';
import type { Message } from '@/api/types';

const ANY = '__any__';

type ViewMode = 'feed' | 'trends';

export function MessagesPage() {
  const [params, setParams] = useSearchParams();
  const view: ViewMode = params.get('view') === 'trends' ? 'trends' : 'feed';

  function setView(v: ViewMode) {
    const next = new URLSearchParams(params);
    if (v === 'feed') next.delete('view');
    else next.set('view', v);
    setParams(next, { replace: true });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Лента сообщений</h1>
          <p className="text-sm text-muted-foreground">
            Поток сообщений и тренды, выявленные ИИ в информационных каналах
          </p>
        </div>
        <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
          <TabsList>
            <TabsTrigger value="feed">Лента</TabsTrigger>
            <TabsTrigger value="trends">
              <Sparkles className="h-3 w-3" /> Тренды недели
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {view === 'feed' ? <FeedView /> : <TrendsView />}
    </div>
  );
}

function FeedView() {
  const [filters, setFilters] = useState<MessageFilters>({});
  const [liveStream, setLiveStream] = useState(false);
  const [liveBuffer, setLiveBuffer] = useState<Message[]>([]);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const query = useMessagesInfinite(filters);

  useMessageStream(liveStream, (msg) => {
    setLiveBuffer((prev) => {
      if (prev.some((m) => m.id === msg.id)) return prev;
      return [msg, ...prev].slice(0, 50);
    });
  });

  useEffect(() => {
    if (!sentinelRef.current) return;
    const el = sentinelRef.current;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && query.hasNextPage && !query.isFetchingNextPage) {
          void query.fetchNextPage();
        }
      },
      { rootMargin: '400px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [query]);

  const items = useMemo(() => {
    const live = liveBuffer;
    const fetched = query.data?.pages.flatMap((p) => p.items) ?? [];
    const seen = new Set<string>();
    return [...live, ...fetched].filter((m) => {
      if (seen.has(m.id)) return false;
      seen.add(m.id);
      return true;
    });
  }, [liveBuffer, query.data]);

  function patch<K extends keyof MessageFilters>(key: K, value: MessageFilters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <>
      <div className="flex justify-end">
        <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2">
          <Radio className={liveStream ? 'h-4 w-4 text-primary' : 'h-4 w-4 text-muted-foreground'} />
          <Label htmlFor="live" className="text-sm">Live</Label>
          <Switch id="live" checked={liveStream} onCheckedChange={setLiveStream} />
        </div>
      </div>

      <Card className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-6">
        <FilterSelect
          label="Канал"
          value={filters.channel_kind}
          onChange={(v) => patch('channel_kind', v)}
          options={[
            { v: 'tg', l: 'Telegram' },
            { v: 'rss', l: 'RSS' },
            { v: 'news', l: 'Новости' },
            { v: 'html', l: 'HTML' },
          ]}
        />
        <FilterSelect
          label="Тональность"
          value={filters.sentiment}
          onChange={(v) => patch('sentiment', v)}
          options={[
            { v: 'positive', l: 'Позитив' },
            { v: 'neutral', l: 'Нейтрально' },
            { v: 'negative', l: 'Негатив' },
          ]}
        />
        <div className="space-y-1">
          <Label className="text-xs">Тема</Label>
          <Input
            placeholder="например, mortgage_rates"
            value={filters.topic ?? ''}
            onChange={(e) => patch('topic', e.target.value || undefined)}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Район</Label>
          <Input
            placeholder="например, presnenskiy"
            value={filters.district ?? ''}
            onChange={(e) => patch('district', e.target.value || undefined)}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">С даты</Label>
          <Input
            type="date"
            value={filters.since ? filters.since.slice(0, 10) : ''}
            onChange={(e) => patch('since', e.target.value ? `${e.target.value}T00:00:00Z` : undefined)}
          />
        </div>
        <FilterSelect
          label="Реклама"
          value={filters.is_ad === undefined ? undefined : String(filters.is_ad)}
          onChange={(v) => patch('is_ad', v === undefined ? undefined : v === 'true')}
          options={[
            { v: 'true', l: 'Только реклама' },
            { v: 'false', l: 'Без рекламы' },
          ]}
        />
      </Card>

      {query.isPending && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}

      {!query.isPending && items.length === 0 && (
        <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
          <Inbox className="h-10 w-10 text-muted-foreground" />
          <h3 className="font-medium">Пока нет сообщений</h3>
          <p className="text-sm text-muted-foreground">
            Попробуйте изменить фильтры или дождаться новых поступлений
          </p>
        </Card>
      )}

      <div className="space-y-3">
        {items.map((m) => (
          <MessageCard key={m.id} message={m} isNew={liveBuffer.some((b) => b.id === m.id)} />
        ))}
      </div>

      <div ref={sentinelRef} className="flex justify-center py-6">
        {query.isFetchingNextPage && <LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" />}
        {!query.hasNextPage && items.length > 0 && (
          <span className="text-xs text-muted-foreground">Конец ленты</span>
        )}
      </div>
    </>
  );
}

function TrendsView() {
  const trends = useTrendsLatest();
  const recompute = useRecomputeTrends();
  const data = trends.data;

  async function handleRecompute() {
    try {
      await recompute.mutateAsync();
      toast.success('Тренды пересчитаны');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Button onClick={handleRecompute} disabled={recompute.isPending} variant="outline" size="sm">
          {recompute.isPending ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCcw className="h-4 w-4" />
          )}
          Пересчитать
        </Button>
      </div>

      {trends.isPending && <Skeleton className="h-96 w-full" />}

      {!trends.isPending && !data && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
            <Sparkles className="h-10 w-10 text-muted-foreground" />
            <h3 className="font-medium">Снимков трендов ещё нет</h3>
            <p className="text-sm text-muted-foreground">
              Нажмите «Пересчитать», чтобы построить первый снимок.
            </p>
          </CardContent>
        </Card>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Период</CardTitle>
            <CardDescription>
              {formatDateTime(data.period_start)} — {formatDateTime(data.period_end)} · обновлено{' '}
              {formatDateTime(data.computed_at)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Тренд</TableHead>
                  <TableHead className="text-right">Упоминаний</TableHead>
                  <TableHead className="text-right">Δ к прошлому</TableHead>
                  <TableHead>Описание</TableHead>
                  <TableHead>Примеры</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((t) => (
                  <TableRow key={t.slug}>
                    <TableCell>
                      <div className="font-medium">{t.title}</div>
                      <div className="font-mono text-[10px] text-muted-foreground">#{t.slug}</div>
                    </TableCell>
                    <TableCell className="text-right text-lg font-semibold">{t.mentions}</TableCell>
                    <TableCell className="text-right">
                      <DeltaBadge delta={t.delta_pct} />
                    </TableCell>
                    <TableCell className="max-w-md text-sm text-muted-foreground">{t.summary}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1.5">
                        {t.sample_ids.slice(0, 5).map((id) => (
                          <Link
                            key={id}
                            to={`/messages/${id}`}
                            className="font-mono text-[10px] text-primary hover:underline"
                          >
                            {id.slice(-6)}
                          </Link>
                        ))}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta === null || delta === undefined) return <Badge variant="muted">новый</Badge>;
  if (delta > 0)
    return (
      <Badge variant="success">
        <TrendingUp className="h-3 w-3" /> +{delta.toFixed(0)}%
      </Badge>
    );
  if (delta < 0)
    return (
      <Badge variant="muted">
        <TrendingDown className="h-3 w-3" /> {delta.toFixed(0)}%
      </Badge>
    );
  return <Badge variant="outline">±0%</Badge>;
}

interface FilterOption {
  v: string;
  l: string;
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
  options: FilterOption[];
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select
        value={value ?? ANY}
        onValueChange={(v) => onChange(v === ANY ? undefined : v)}
      >
        <SelectTrigger>
          <SelectValue placeholder="Все" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Все</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.v} value={o.v}>
              {o.l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
