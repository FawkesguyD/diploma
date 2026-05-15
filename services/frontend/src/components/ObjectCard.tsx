import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ExternalLink, Heart, MapPin, Ruler, BedDouble, TrendingDown } from 'lucide-react';
import type { RealEstateObject } from '@/api/types';
import { cn, formatNumber, formatPrice } from '@/lib/utils';
import { useAddFavorite, useFavorites, useRemoveFavorite } from '@/api/hooks';

export function ObjectCard({ object }: { object: RealEstateObject }) {
  const l = object.listing ?? {};
  const addr = (l.address && typeof l.address === 'object' ? l.address : null) as
    | { raw?: string; city?: string; district_slug?: string }
    | null;
  const city = (l.city as string | undefined) ?? addr?.city;
  const district = (l.district as string | undefined) ?? addr?.district_slug;
  const ev = object.evaluation;
  const undervalued = ev?.is_undervalued;
  const dev = ev?.deviation_pct;
  const favs = useFavorites('object');
  const add = useAddFavorite();
  const rem = useRemoveFavorite();
  const isFav = (favs.data ?? []).some((f) => f.target_ref === object.id);

  function toggleFav(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const payload = { target_kind: 'object' as const, target_ref: object.id };
    if (isFav) rem.mutate(payload);
    else add.mutate(payload);
  }

  return (
    <Card className={cn('relative transition-all hover:shadow-md', undervalued && 'border-emerald/40 ring-1 ring-emerald/20')}>
      <button
        type="button"
        onClick={toggleFav}
        className="absolute right-3 top-3 z-10 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-rose-500"
        aria-label={isFav ? 'Убрать из избранного' : 'В избранное'}
      >
        <Heart className={cn('h-4 w-4', isFav && 'fill-rose-500 text-rose-500')} />
      </button>
      <CardHeader className="pb-3">
        <CardTitle className="line-clamp-2 text-base">
          {l.title || `${l.rooms ?? '?'}-к, ${formatNumber(l.area)} м²`}
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-xs text-muted-foreground">
          {district && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {district}
            </span>
          )}
          {city && <span>· {city}</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-2xl font-semibold tracking-tight">{formatPrice(l.price)}</div>
            {l.price_per_m2 && (
              <div className="text-xs text-muted-foreground">{formatNumber(l.price_per_m2)} ₽/м²</div>
            )}
          </div>
          {ev && (
            <div className="text-right">
              {ev.predicted_price !== undefined && (
                <div className="text-xs text-muted-foreground">оценка: {formatPrice(ev.predicted_price)}</div>
              )}
              {dev !== undefined && (
                <Badge variant={dev < 0 ? 'success' : 'muted'} className="mt-1">
                  {dev < 0 && <TrendingDown className="mr-0.5 h-3 w-3" />}
                  {dev > 0 ? '+' : ''}
                  {dev.toFixed(1)}%
                </Badge>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {l.rooms !== undefined && (
            <span className="inline-flex items-center gap-1">
              <BedDouble className="h-3 w-3" /> {l.rooms} комн.
            </span>
          )}
          {l.area !== undefined && (
            <span className="inline-flex items-center gap-1">
              <Ruler className="h-3 w-3" /> {formatNumber(l.area)} м²
            </span>
          )}
          {l.floor !== undefined && (
            <span>
              этаж {l.floor}
              {l.total_floors ? `/${l.total_floors}` : ''}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between border-t pt-3 text-xs">
          <Badge variant="outline" className="font-mono">
            {object.channel_site}
          </Badge>
          {object.url && (
            <a
              href={object.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              Открыть <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
