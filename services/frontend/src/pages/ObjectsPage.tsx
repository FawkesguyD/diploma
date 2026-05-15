import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useObjects, useTopUndervalued, type ObjectFilters } from '@/api/hooks';
import { ObjectCard } from '@/components/ObjectCard';
import { ObjectDetailDialog } from '@/components/ObjectDetailDialog';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Building2, TrendingDown } from 'lucide-react';
import type { RealEstateObject } from '@/api/types';

type ViewMode = 'all' | 'top';

export function ObjectsPage() {
  const [params, setParams] = useSearchParams();
  const initialTop = params.get('undervalued') === '1' || params.get('view') === 'top';
  const [view, setView] = useState<ViewMode>(initialTop ? 'top' : 'all');
  const [filters, setFilters] = useState<ObjectFilters>(initialTop ? { is_undervalued: true } : {});
  const [selectedId, setSelectedId] = useState<string | null>(params.get('focus'));

  const all = useObjects(view === 'all' ? filters : {});
  const top = useTopUndervalued({
    city: filters.city || undefined,
    district: filters.district || undefined,
    limit: 30,
  });

  function patch<K extends keyof ObjectFilters>(k: K, v: ObjectFilters[K]) {
    setFilters((p) => ({ ...p, [k]: v }));
  }

  function switchView(v: ViewMode) {
    setView(v);
    const next = new URLSearchParams(params);
    if (v === 'top') next.set('view', 'top');
    else next.delete('view');
    next.delete('undervalued');
    setParams(next, { replace: true });
  }

  const items: RealEstateObject[] = useMemo(() => {
    if (view === 'top') return top.data ?? [];
    return all.data?.items ?? [];
  }, [view, all.data, top.data]);

  const isPending = view === 'top' ? top.isPending : all.isPending;

  useEffect(() => {
    const focus = params.get('focus');
    if (focus) setSelectedId(focus);
  }, [params]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Объекты недвижимости</h1>
          <p className="text-sm text-muted-foreground">
            Объявления с площадок + оценка модели рыночной стоимости
          </p>
        </div>
        <Tabs value={view} onValueChange={(v) => switchView(v as ViewMode)}>
          <TabsList>
            <TabsTrigger value="all">
              <Building2 className="h-3 w-3" /> Все
            </TabsTrigger>
            <TabsTrigger value="top">
              <TrendingDown className="h-3 w-3" /> Топ недооценённых
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <Card
        className={
          view === 'top'
            ? 'grid grid-cols-1 gap-3 p-4 sm:grid-cols-2'
            : 'grid grid-cols-2 gap-3 p-4 lg:grid-cols-7'
        }
      >
        <Field label="Город">
          <Input
            value={filters.city ?? ''}
            placeholder="Москва"
            onChange={(e) => patch('city', e.target.value || undefined)}
          />
        </Field>
        <Field label="Район">
          <Input
            value={filters.district ?? ''}
            placeholder="presnenskiy"
            onChange={(e) => patch('district', e.target.value || undefined)}
          />
        </Field>
        {view === 'all' && (
          <>
            <Field label="Комнаты">
              <Input
                type="number"
                min={0}
                value={filters.rooms ?? ''}
                onChange={(e) => patch('rooms', e.target.value ? Number(e.target.value) : undefined)}
              />
            </Field>
            <Field label="Цена от">
              <Input
                type="number"
                value={filters.price_min ?? ''}
                onChange={(e) => patch('price_min', e.target.value ? Number(e.target.value) : undefined)}
              />
            </Field>
            <Field label="Цена до">
              <Input
                type="number"
                value={filters.price_max ?? ''}
                onChange={(e) => patch('price_max', e.target.value ? Number(e.target.value) : undefined)}
              />
            </Field>
            <Field label="Площадь м² от/до">
              <div className="flex gap-1">
                <Input
                  type="number"
                  value={filters.area_min ?? ''}
                  onChange={(e) => patch('area_min', e.target.value ? Number(e.target.value) : undefined)}
                />
                <Input
                  type="number"
                  value={filters.area_max ?? ''}
                  onChange={(e) => patch('area_max', e.target.value ? Number(e.target.value) : undefined)}
                />
              </div>
            </Field>
            <Field label="Только недооценённые">
              <div className="flex h-9 items-center">
                <Switch
                  checked={filters.is_undervalued ?? false}
                  onCheckedChange={(v) => patch('is_undervalued', v || undefined)}
                />
              </div>
            </Field>
          </>
        )}
      </Card>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      )}

      {!isPending && items.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
            {view === 'top' ? (
              <TrendingDown className="h-10 w-10 text-muted-foreground" />
            ) : (
              <Building2 className="h-10 w-10 text-muted-foreground" />
            )}
            <h3 className="font-medium">
              {view === 'top' ? 'Пока нет недооценённых объектов' : 'Нет объектов'}
            </h3>
            <p className="text-sm text-muted-foreground">
              {view === 'top'
                ? 'Запустите модель оценки или дождитесь завершения текущего ранжирования.'
                : 'Парсеры площадок ещё не собрали данные либо фильтры слишком узкие.'}
            </p>
          </CardContent>
        </Card>
      )}

      {items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((o) => (
            <div key={o.id} onClick={() => setSelectedId(o.id)} className="cursor-pointer">
              <ObjectCard object={o} />
            </div>
          ))}
        </div>
      )}

      <ObjectDetailDialog
        objectId={selectedId}
        open={selectedId !== null}
        onOpenChange={(o) => !o && setSelectedId(null)}
      />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}
