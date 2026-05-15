import { useEffect, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, Tooltip as MapTooltip } from 'react-leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { Layer, PathOptions } from 'leaflet';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { usePricesByDistrict } from '@/api/hooks';
import { formatNumber } from '@/lib/utils';
import { Map as MapIcon } from 'lucide-react';

interface DistrictProps {
  slug: string;
  name?: string;
}

export function MapPage() {
  const [geo, setGeo] = useState<FeatureCollection<Geometry, DistrictProps> | null>(null);
  const [geoErr, setGeoErr] = useState<string | null>(null);
  const prices = usePricesByDistrict();

  useEffect(() => {
    fetch('/geo/moscow-districts.geojson')
      .then((r) => r.json())
      .then((d: FeatureCollection<Geometry, DistrictProps>) => setGeo(d))
      .catch((err: Error) => setGeoErr(err.message));
  }, []);

  const priceMap = new Map<string, number>();
  for (const p of prices.data ?? []) {
    const v = p.avg_price_per_m2 ?? p.avg_price;
    if (v !== undefined) priceMap.set(p.district_slug, v);
  }

  const values = Array.from(priceMap.values());
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;

  function colorFor(slug: string | undefined): string {
    if (!slug) return 'hsl(240, 5%, 90%)';
    const v = priceMap.get(slug);
    if (v === undefined) return 'hsl(240, 5%, 88%)';
    const t = max === min ? 0.5 : (v - min) / (max - min);
    const lightness = 70 - t * 35;
    return `hsl(262, 70%, ${lightness}%)`;
  }

  function styleFn(feature?: Feature<Geometry, DistrictProps>): PathOptions {
    return {
      fillColor: colorFor(feature?.properties?.slug),
      weight: 1,
      color: 'hsl(240, 4%, 35%)',
      fillOpacity: 0.7,
    };
  }

  function onEachFeature(feature: Feature<Geometry, DistrictProps>, layer: Layer) {
    const slug = feature.properties.slug;
    const name = feature.properties.name ?? slug;
    const v = priceMap.get(slug);
    layer.bindTooltip(
      `<div style="font-family: Inter, sans-serif"><b>${name}</b><br/><small>${slug}</small><br/>${
        v !== undefined ? `${formatNumber(v)} ₽/м²` : 'нет данных'
      }</div>`,
      { sticky: true }
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Карта районов</h1>
        <p className="text-sm text-muted-foreground">
          Цвет районов соответствует средней цене ₽/м² по данным метрик
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <MapIcon className="h-4 w-4 text-primary" /> Москва
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!geo && !geoErr && <Skeleton className="h-[600px] w-full" />}
          {geoErr && (
            <div className="flex h-[600px] items-center justify-center text-sm text-muted-foreground">
              Не удалось загрузить GeoJSON: {geoErr}
            </div>
          )}
          {geo && (
            <div className="h-[600px] overflow-hidden rounded-md border">
              <MapContainer center={[55.751244, 37.618423]} zoom={10} style={{ height: '100%', width: '100%' }}>
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <GeoJSON data={geo} style={styleFn} onEachFeature={onEachFeature}>
                  <MapTooltip sticky />
                </GeoJSON>
              </MapContainer>
            </div>
          )}

          {values.length > 0 && (
            <div className="mt-4 flex items-center gap-3 text-xs text-muted-foreground">
              <span>{formatNumber(min)} ₽/м²</span>
              <div
                className="h-2 flex-1 rounded-full"
                style={{
                  background: 'linear-gradient(to right, hsl(262, 70%, 70%), hsl(262, 70%, 35%))',
                }}
              />
              <span>{formatNumber(max)} ₽/м²</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
