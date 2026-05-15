import { useEffect, useMemo, useRef, useState } from 'react';
import { useMessagesInfinite, type MessageFilters } from '@/api/hooks';
import { useMessageStream } from '@/api/useMessageStream';
import { MessageCard } from '@/components/MessageCard';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card } from '@/components/ui/card';
import { Inbox, LoaderCircle, Radio } from 'lucide-react';
import type { Message } from '@/api/types';

const ANY = '__any__';

export function MessagesPage() {
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Лента сообщений</h1>
          <p className="text-sm text-muted-foreground">
            Поток сообщений из Telegram, RSS и новостных источников с NLP-аннотациями
          </p>
        </div>
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
    </div>
  );
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
