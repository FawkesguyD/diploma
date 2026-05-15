import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { cn, formatDateTime } from '@/lib/utils';
import { ExternalLink, Heart, MessageSquare } from 'lucide-react';
import type { Message, SentimentLabel } from '@/api/types';
import { useAddFavorite, useFavorites, useRemoveFavorite } from '@/api/hooks';

const SENTIMENT_LABEL: Record<SentimentLabel, string> = {
  positive: 'Позитив',
  neutral: 'Нейтрально',
  negative: 'Негатив',
};

const SENTIMENT_CLASS: Record<SentimentLabel, string> = {
  positive: 'bg-emerald/10 text-emerald',
  negative: 'bg-rose/10 text-rose',
  neutral: 'bg-slate/10 text-slate',
};

const CHANNEL_LABEL: Record<string, string> = {
  tg: 'Telegram',
  rss: 'RSS',
  news: 'Новости',
  html: 'HTML',
};

export function MessageCard({ message, isNew }: { message: Message; isNew?: boolean }) {
  const sentiment = message.annotation?.sentiment?.label;
  const topics = message.annotation?.topics ?? [];
  const isAd = message.annotation?.is_ad;
  const favs = useFavorites('message');
  const add = useAddFavorite();
  const rem = useRemoveFavorite();
  const isFav = (favs.data ?? []).some((f) => f.target_ref === message.id);

  function toggleFav(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const payload = { target_kind: 'message' as const, target_ref: message.id };
    if (isFav) rem.mutate(payload);
    else add.mutate(payload);
  }

  return (
    <article
      className={cn(
        'group relative overflow-hidden rounded-lg border bg-card p-5 shadow-sm transition-all hover:shadow-md',
        isNew && 'ring-2 ring-primary/40'
      )}
    >
      <button
        type="button"
        onClick={toggleFav}
        className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-rose-500"
        aria-label={isFav ? 'Убрать из избранного' : 'В избранное'}
      >
        <Heart className={cn('h-4 w-4', isFav && 'fill-rose-500 text-rose-500')} />
      </button>
      <header className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className="font-mono">
          {CHANNEL_LABEL[message.channel_kind] ?? message.channel_kind}
        </Badge>
        <span className="font-medium text-foreground">
          {message.author?.name || message.author?.handle || message.channel_site}
        </span>
        <span className="text-muted-foreground">•</span>
        <time className="text-muted-foreground">{formatDateTime(message.published_at)}</time>
        {message.lang && <Badge variant="muted">{message.lang}</Badge>}
        {isAd && <Badge variant="warning">Реклама</Badge>}
      </header>

      <Link to={`/messages/${message.id}`} className="block space-y-3">
        <p className="line-clamp-4 whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
          {message.text}
        </p>

        <div className="flex flex-wrap items-center gap-1.5">
          {sentiment && (
            <span
              className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium', SENTIMENT_CLASS[sentiment])}
            >
              {SENTIMENT_LABEL[sentiment]}
            </span>
          )}
          {topics.slice(0, 5).map((t) => (
            <Badge key={t.slug} variant="secondary" className="font-mono text-[10px]">
              #{t.slug}
            </Badge>
          ))}
        </div>
      </Link>

      <footer className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <MessageSquare className="h-3 w-3" />
          {message.channel_site}
        </span>
        {message.url && (
          <a
            href={message.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 hover:text-primary"
            onClick={(e) => e.stopPropagation()}
          >
            Источник <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </footer>
    </article>
  );
}
