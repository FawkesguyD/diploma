import { useTopUndervalued } from '@/api/hooks';
import { ObjectCard } from '@/components/ObjectCard';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { TrendingDown } from 'lucide-react';

export function TopUndervaluedPage() {
  const [city, setCity] = useState('');
  const [district, setDistrict] = useState('');
  const { data, isPending } = useTopUndervalued({
    city: city || undefined,
    district: district || undefined,
    limit: 30,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Топ недооценённых объектов</h1>
        <p className="text-sm text-muted-foreground">
          Объекты, цена которых ниже предсказанной моделью оценки
        </p>
      </div>

      <Card className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
        <div className="space-y-1">
          <Label className="text-xs">Город</Label>
          <Input value={city} placeholder="Москва" onChange={(e) => setCity(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Район</Label>
          <Input value={district} placeholder="presnenskiy" onChange={(e) => setDistrict(e.target.value)} />
        </div>
      </Card>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      )}

      {!isPending && data && data.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center">
            <TrendingDown className="h-10 w-10 text-muted-foreground" />
            <h3 className="font-medium">Пока нет недооценённых объектов</h3>
            <p className="text-sm text-muted-foreground">
              Запустите модель оценки или дождитесь завершения текущего ранжирования
            </p>
          </CardContent>
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((o) => (
            <ObjectCard key={o.id} object={o} />
          ))}
        </div>
      )}
    </div>
  );
}
