import { useObject } from '@/api/hooks';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { ExternalLink, TrendingDown, TrendingUp } from 'lucide-react';
import { formatNumber, formatPrice, formatDateTime } from '@/lib/utils';

interface Props {
  objectId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type AddressObj = { raw?: string; city?: string; district_slug?: string; lat?: number; lon?: number };

function addrText(addr: unknown, listing: Record<string, unknown>): string {
  if (typeof addr === 'string' && addr) return addr;
  if (addr && typeof addr === 'object') {
    const a = addr as AddressObj;
    return a.raw || [a.city, a.district_slug].filter(Boolean).join(', ') || '—';
  }
  const city = listing.city as string | undefined;
  const district = listing.district as string | undefined;
  return [city, district].filter(Boolean).join(', ') || '—';
}

export function ObjectDetailDialog({ objectId, open, onOpenChange }: Props) {
  const { data, isPending } = useObject(objectId ?? undefined);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        {isPending || !data ? (
          <>
            <DialogHeader>
              <DialogTitle>Загрузка объекта…</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="line-clamp-2 text-lg">
                {(data.listing.title as string | undefined) ||
                  `${data.listing.rooms ?? '?'}-к, ${formatNumber(data.listing.area as number | undefined)} м²`}
              </DialogTitle>
              <DialogDescription>
                {addrText(data.listing.address, data.listing as Record<string, unknown>)}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 max-h-[70vh] overflow-y-auto">
              <section className="flex items-baseline justify-between rounded-md border bg-muted/30 p-4">
                <div>
                  <div className="text-3xl font-semibold tracking-tight">{formatPrice(data.listing.price)}</div>
                  {data.listing.price_per_m2 && (
                    <div className="text-xs text-muted-foreground">
                      {formatNumber(data.listing.price_per_m2)} ₽/м²
                    </div>
                  )}
                </div>
                {data.evaluation && (
                  <div className="text-right">
                    <div className="text-xs text-muted-foreground">Оценка модели</div>
                    <div className="text-lg font-semibold">{formatPrice(data.evaluation.predicted_price)}</div>
                    {data.evaluation.deviation_pct !== undefined && (
                      <DeviationBadge dev={data.evaluation.deviation_pct} undervalued={data.evaluation.is_undervalued} />
                    )}
                  </div>
                )}
              </section>

              <section>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Характеристики
                </h4>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  {Object.entries(data.listing).map(([k, v]) => {
                    if (v === null || v === undefined || v === '') return null;
                    if (Array.isArray(v) || typeof v === 'object') return null;
                    return (
                      <div key={k} className="contents">
                        <dt className="text-muted-foreground">{labelFor(k)}</dt>
                        <dd className="font-medium">{String(v)}</dd>
                      </div>
                    );
                  })}
                </dl>
              </section>

              {data.evaluation && (
                <section>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Оценка модели
                  </h4>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    <dt className="text-muted-foreground">Модель</dt>
                    <dd className="font-mono">{data.evaluation.model_version ?? '—'}</dd>
                    <dt className="text-muted-foreground">Прогноз</dt>
                    <dd className="font-medium">{formatPrice(data.evaluation.predicted_price)}</dd>
                    <dt className="text-muted-foreground">Отклонение</dt>
                    <dd className="font-medium">
                      {data.evaluation.deviation_abs !== undefined && formatPrice(data.evaluation.deviation_abs)}
                      {data.evaluation.deviation_pct !== undefined && ` (${data.evaluation.deviation_pct.toFixed(1)}%)`}
                    </dd>
                    <dt className="text-muted-foreground">Рассчитано</dt>
                    <dd>{formatDateTime(data.evaluation.computed_at)}</dd>
                  </dl>
                </section>
              )}

              <section className="flex items-center justify-between border-t pt-3">
                <Badge variant="outline" className="font-mono">
                  {data.channel_site}
                </Badge>
                {data.url && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={data.url} target="_blank" rel="noreferrer noopener">
                      Открыть исходник <ExternalLink className="h-3 w-3" />
                    </a>
                  </Button>
                )}
              </section>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DeviationBadge({ dev, undervalued }: { dev: number; undervalued?: boolean }) {
  if (dev < 0)
    return (
      <Badge variant={undervalued ? 'success' : 'muted'} className="mt-1">
        <TrendingDown className="h-3 w-3" /> {dev.toFixed(1)}%
      </Badge>
    );
  return (
    <Badge variant="muted" className="mt-1">
      <TrendingUp className="h-3 w-3" /> +{dev.toFixed(1)}%
    </Badge>
  );
}

const LABELS: Record<string, string> = {
  title: 'Название',
  city: 'Город',
  district: 'Район',
  address: 'Адрес',
  price: 'Цена',
  price_per_m2: 'Цена ₽/м²',
  area: 'Площадь, м²',
  rooms: 'Комнат',
  floor: 'Этаж',
  total_floors: 'Этажей всего',
  description: 'Описание',
};

function labelFor(key: string): string {
  return LABELS[key] ?? key;
}
