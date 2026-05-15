import { useState } from 'react';
import { useObjects, type ObjectFilters } from '@/api/hooks';
import { ObjectCard } from '@/components/ObjectCard';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Building2 } from 'lucide-react';

export function ObjectsPage() {
  const [filters, setFilters] = useState<ObjectFilters>({});
  const { data, isPending } = useObjects(filters);

  function patch<K extends keyof ObjectFilters>(k: K, v: ObjectFilters[K]) {
    setFilters((p) => ({ ...p, [k]: v }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Объекты недвижимости</h1>
        <p className="text-sm text-muted-foreground">
          Объявления с площадок недвижимости + оценка модели рыночной стоимости
        </p>
      </div>

      <Card className="grid grid-cols-2 gap-3 p-4 lg:grid-cols-7">
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
      </Card>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      )}

      {!isPending && data && data.items.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
            <Building2 className="h-10 w-10 text-muted-foreground" />
            <h3 className="font-medium">Нет объектов</h3>
            <p className="text-sm text-muted-foreground">Парсеры площадок ещё не собрали данные либо фильтры слишком узкие.</p>
          </CardContent>
        </Card>
      )}

      {data && data.items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((o) => (
            <ObjectCard key={o.id} object={o} />
          ))}
        </div>
      )}
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
