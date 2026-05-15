import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Heart, Trash2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { api, extractErrorMessage } from '@/api/client';
import { useFavorites, useRemoveFavorite } from '@/api/hooks';
import { cn, formatPrice } from '@/lib/utils';
import type { Favorite, Message, RealEstateObject } from '@/api/types';

export function FavoritesPopover() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'message' | 'object'>('message');
  const favs = useFavorites(tab);
  const count = (favs.data ?? []).length;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Избранное" className="relative">
          <Heart className="h-4 w-4" />
          {count > 0 && (
            <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
              {count}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[380px] p-0">
        <div className="border-b px-3 py-2">
          <div className="text-sm font-semibold">Избранное</div>
        </div>
        <Tabs value={tab} onValueChange={(v) => setTab(v as 'message' | 'object')}>
          <div className="px-3 pt-2">
            <TabsList className="w-full">
              <TabsTrigger value="message" className="flex-1">Сообщения</TabsTrigger>
              <TabsTrigger value="object" className="flex-1">Объекты</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="message" className="mt-0 max-h-[420px] overflow-y-auto p-3">
            <FavList favs={favs.data ?? []} kind="message" isPending={favs.isPending} onClose={() => setOpen(false)} />
          </TabsContent>
          <TabsContent value="object" className="mt-0 max-h-[420px] overflow-y-auto p-3">
            <FavList favs={favs.data ?? []} kind="object" isPending={favs.isPending} onClose={() => setOpen(false)} />
          </TabsContent>
        </Tabs>
      </PopoverContent>
    </Popover>
  );
}

function FavList({
  favs,
  kind,
  isPending,
  onClose,
}: {
  favs: Favorite[];
  kind: 'message' | 'object';
  isPending: boolean;
  onClose: () => void;
}) {
  const remove = useRemoveFavorite();
  const queries = useQueries({
    queries: favs.map((f) => ({
      queryKey: [f.target_kind, f.target_ref, 'fav-popover'],
      queryFn: async () => {
        const path = f.target_kind === 'message' ? `/messages/${f.target_ref}` : `/objects/${f.target_ref}`;
        return (await api.get<Message | RealEstateObject>(path)).data;
      },
    })),
  });

  async function handleRemove(ref: string) {
    try {
      await remove.mutateAsync({ target_kind: kind, target_ref: ref });
      toast.success('Удалено из избранного');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  if (isPending) return <Skeleton className="h-32 w-full" />;
  if (favs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <Heart className="h-7 w-7 text-muted-foreground" />
        <div className="text-sm font-medium">Здесь пусто</div>
        <div className="px-4 text-xs text-muted-foreground">
          Нажмите на сердечко в карточке, чтобы добавить {kind === 'message' ? 'сообщение' : 'объект'}.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {favs.map((f, i) => {
        const q = queries[i];
        if (q.isPending) return <Skeleton key={f.id} className="h-14 w-full" />;
        if (!q.data) {
          return (
            <div key={f.id} className="flex items-center justify-between rounded-md border p-2 text-xs">
              <span className="text-muted-foreground">Не удалось загрузить</span>
              <Button variant="ghost" size="sm" onClick={() => handleRemove(f.target_ref)}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          );
        }
        if (f.target_kind === 'message') {
          const m = q.data as Message;
          return (
            <FavRow
              key={f.id}
              title={m.author?.name || m.author?.handle || m.channel_site}
              subtitle={m.text}
              badge={m.channel_kind}
              href={`/messages/${m.id}`}
              onOpen={onClose}
              onRemove={() => handleRemove(f.target_ref)}
            />
          );
        }
        const o = q.data as RealEstateObject;
        const title =
          (o.listing?.title as string | undefined) ||
          `${o.listing?.rooms ?? '?'}-к · ${formatPrice(o.listing?.price)}`;
        return (
          <FavRow
            key={f.id}
            title={title}
            subtitle={(o.listing?.address as string | undefined) ?? o.channel_site}
            badge={o.channel_site}
            href={`/objects?focus=${o.id}`}
            external={o.url}
            onOpen={onClose}
            onRemove={() => handleRemove(f.target_ref)}
          />
        );
      })}
    </div>
  );
}

function FavRow({
  title,
  subtitle,
  badge,
  href,
  external,
  onOpen,
  onRemove,
}: {
  title: string;
  subtitle?: string;
  badge: string;
  href: string;
  external?: string | null;
  onOpen: () => void;
  onRemove: () => void;
}) {
  return (
    <div className={cn('group flex items-start gap-2 rounded-md border p-2 hover:bg-accent/40')}>
      <Link to={href} onClick={onOpen} className="min-w-0 flex-1 space-y-0.5">
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className="font-mono text-[9px]">{badge}</Badge>
          <span className="truncate text-sm font-medium">{title}</span>
        </div>
        {subtitle && <p className="line-clamp-2 text-xs text-muted-foreground">{subtitle}</p>}
      </Link>
      <div className="flex flex-col items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        {external && (
          <a
            href={external}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Открыть источник"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-destructive"
          aria-label="Удалить"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
