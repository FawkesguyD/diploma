import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { cn, formatDateTime } from '@/lib/utils';
import { ExternalLink, MessageSquare } from 'lucide-react';
import type { Message, SentimentLabel } from '@/api/types';

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

  return (
    <article
      className={cn(
        'group relative overflow-hidden rounded-lg border bg-card p-5 shadow-sm transition-all hover:shadow-md',
        isNew && 'ring-2 ring-primary/40'
      )}
    >
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
