import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L, { divIcon, type GeoJSON as LeafletGeoJSON, type Layer, type PathOptions } from 'leaflet';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { usePricesByDistrict, useSentimentByDistrict, useTopUndervalued } from '@/api/hooks';
import type { RealEstateObject } from '@/api/types';
import { formatNumber } from '@/lib/utils';
import { ArrowRight, Map as MapIcon, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';

function undervaluedIcon(deviation: number): L.DivIcon {
  const r = Math.min(14, 6 + Math.abs(deviation) / 5);
  const d = r * 2;
  return divIcon({
    className: 'aisi-undervalued-marker',
    html: `<span style="display:block;width:${d}px;height:${d}px;border-radius:9999px;background:#ef4444;border:1px solid #dc2626;opacity:0.85;box-shadow:0 0 0 1px rgba(255,255,255,0.6)"></span>`,
    iconSize: [d, d],
    iconAnchor: [r, r],
  });
}

function clusterIcon(cluster: { getChildCount(): number }): L.DivIcon {
  const n = cluster.getChildCount();
  const size = n < 10 ? 32 : n < 50 ? 38 : 46;
  return divIcon({
    className: 'aisi-cluster',
    html: `<div style="display:flex;align-items:center;justify-content:center;width:${size}px;height:${size}px;border-radius:9999px;background:rgba(239,68,68,0.85);color:white;font-weight:600;font-size:12px;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.25)">${n}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

interface DistrictProps {
  slug: string;
  name?: string;
}

type Mode = 'price' | 'sentiment';

function FlyTo({ target }: { target: { lat: number; lon: number; zoom: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], target.zoom, { duration: 0.8 });
  }, [target, map]);
  return null;
}

function centroid(geom: Geometry): [number, number] | null {
  const collect = (coords: unknown, acc: [number, number][]): void => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      acc.push([coords[0] as number, coords[1] as number]);
      return;
    }
    for (const c of coords) collect(c, acc);
  };
  const pts: [number, number][] = [];
  if ('coordinates' in geom) collect(geom.coordinates as unknown, pts);
  if (!pts.length) return null;
  const lon = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const lat = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  return [lat, lon];
}

export function MapPage() {
  const navigate = useNavigate();
  const [geo, setGeo] = useState<FeatureCollection<Geometry, DistrictProps> | null>(null);
  const [geoErr, setGeoErr] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('price');
  const [query, setQuery] = useState('');
  const [showUndervalued, setShowUndervalued] = useState(true);
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom: number } | null>(null);
  const geoLayerRef = useRef<LeafletGeoJSON | null>(null);

  const prices = usePricesByDistrict();
  const sentiment = useSentimentByDistrict();
  const undervalued = useTopUndervalued({ city: 'Moscow', limit: 200 });

  useEffect(() => {
    fetch('/geo/moscow-districts.geojson')
      .then((r) => r.json())
      .then((d: FeatureCollection<Geometry, DistrictProps>) => setGeo(d))
      .catch((err: Error) => setGeoErr(err.message));
  }, []);

  const priceMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of prices.data ?? []) {
      const v = p.avg_price_per_m2 ?? p.avg_price;
      if (v !== undefined) m.set(p.district_slug, v);
    }
    return m;
  }, [prices.data]);

  const sentimentMap = useMemo(() => {
    const m = new Map<string, { avg: number; total: number; pos: number; neu: number; neg: number }>();
    for (const s of sentiment.data ?? []) {
      m.set(s.district_slug, {
        avg: s.sentiment_avg,
        total: s.messages_total,
        pos: s.pos_count,
        neu: s.neu_count,
        neg: s.neg_count,
      });
    }
    return m;
  }, [sentiment.data]);

  const centroidMap = useMemo(() => {
    const m = new Map<string, [number, number]>();
    for (const f of geo?.features ?? []) {
      const c = centroid(f.geometry);
      if (c) m.set(f.properties.slug, c);
    }
    return m;
  }, [geo]);

  const districtOptions = useMemo(() => {
    const list = (geo?.features ?? []).map((f) => ({
      slug: f.properties.slug,
      name: f.properties.name ?? f.properties.slug,
    }));
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return list
      .filter((d) => d.slug.toLowerCase().includes(q) || d.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [geo, query]);

  const priceRange = useMemo(() => {
    const v = Array.from(priceMap.values());
    return { min: v.length ? Math.min(...v) : 0, max: v.length ? Math.max(...v) : 1 };
  }, [priceMap]);

  function colorFor(slug: string | undefined): string {
    if (!slug) return 'hsl(240, 5%, 90%)';
    if (mode === 'price') {
      const v = priceMap.get(slug);
      if (v === undefined) return 'hsl(240, 5%, 88%)';
      const t = priceRange.max === priceRange.min ? 0.5 : (v - priceRange.min) / (priceRange.max - priceRange.min);
      const lightness = 70 - t * 35;
      return `hsl(262, 70%, ${lightness}%)`;
    }
    const s = sentimentMap.get(slug);
    if (!s) return 'hsl(240, 5%, 88%)';
    const t = Math.max(-1, Math.min(1, s.avg));
    const hue = ((t + 1) / 2) * 120;
    return `hsl(${hue}, 65%, 55%)`;
  }

  function styleFn(feature?: Feature<Geometry, DistrictProps>): PathOptions {
    return {
      fillColor: colorFor(feature?.properties?.slug),
      weight: 1,
      color: 'hsl(240, 4%, 35%)',
      fillOpacity: 0.65,
    };
  }

  function tooltipHtml(slug: string, name: string): string {
    const price = priceMap.get(slug);
    const sent = sentimentMap.get(slug);
    return `<div style="font-family: Inter, sans-serif; min-width: 180px">
      <b>${name}</b><br/><small style="color:#888">${slug}</small>
      <hr style="border:none;border-top:1px solid #eee;margin:4px 0"/>
      <div>Цена: ${price !== undefined ? `${formatNumber(price)} ₽/м²` : '—'}</div>
      <div>Тональность: ${sent ? sent.avg.toFixed(2) : '—'}${sent ? ` (${sent.total} сообщ.)` : ''}</div>
    </div>`;
  }

  function onEachFeature(feature: Feature<Geometry, DistrictProps>, layer: Layer) {
    const slug = feature.properties.slug;
    const name = feature.properties.name ?? slug;
    layer.bindTooltip(tooltipHtml(slug, name), { sticky: true });
    layer.on('click', () => {
      const c = centroidMap.get(slug);
      if (c) setFlyTarget({ lat: c[0], lon: c[1], zoom: 13 });
    });
  }

  useEffect(() => {
    geoLayerRef.current?.setStyle(styleFn);
    geoLayerRef.current?.eachLayer((l) => {
      const f = (l as unknown as { feature: Feature<Geometry, DistrictProps> }).feature;
      if (f) (l as Layer).bindTooltip(tooltipHtml(f.properties.slug, f.properties.name ?? f.properties.slug), { sticky: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, priceMap, sentimentMap]);

  function selectDistrict(slug: string) {
    const c = centroidMap.get(slug);
    if (c) setFlyTarget({ lat: c[0], lon: c[1], zoom: 13 });
    setQuery('');
  }

  const undervaluedPoints = useMemo(() => {
    return (undervalued.data ?? [])
      .map((o) => {
        const addr = o.listing?.address as unknown;
        let lat: number | undefined;
        let lon: number | undefined;
        if (addr && typeof addr === 'object') {
          const a = addr as { lat?: number; lon?: number };
          lat = a.lat;
          lon = a.lon;
        }
        if ((lat === undefined || lon === undefined) && o.listing?.geo) {
          lat = o.listing.geo.lat;
          lon = o.listing.geo.lon;
        }
        if (lat === undefined || lon === undefined) return null;
        return { o, lat, lon };
      })
      .filter((x): x is { o: RealEstateObject; lat: number; lon: number } => Boolean(x));
  }, [undervalued.data]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Карта районов</h1>
        <p className="text-sm text-muted-foreground">
          Поиск районов, переключение слоёв «цена / тональность», маркеры топ-недооценённых объектов
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span className="flex items-center gap-2">
              <MapIcon className="h-4 w-4 text-primary" /> Москва
            </span>
            <div className="flex flex-wrap items-center gap-3">
              <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
                <TabsList>
                  <TabsTrigger value="price">Цена ₽/м²</TabsTrigger>
                  <TabsTrigger value="sentiment">Тональность</TabsTrigger>
                </TabsList>
              </Tabs>
              <label className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
                <Switch checked={showUndervalued} onCheckedChange={setShowUndervalued} />
                Недооценённые
              </label>
              <div className="relative w-56">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Поиск района…"
                  className="h-8 pl-7 text-xs"
                />
                {districtOptions.length > 0 && (
                  <div className="absolute left-0 right-0 top-full z-[1000] mt-1 max-h-64 overflow-auto rounded-md border bg-popover p-1 shadow-md">
                    {districtOptions.map((d) => (
                      <button
                        key={d.slug}
                        type="button"
                        onClick={() => selectDistrict(d.slug)}
                        className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-accent"
                      >
                        <span>{d.name}</span>
                        <span className="text-muted-foreground">{d.slug}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
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
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
                  url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                  subdomains={['a', 'b', 'c', 'd']}
                  maxZoom={19}
                />
                <GeoJSON
                  data={geo}
                  style={styleFn}
                  onEachFeature={onEachFeature}
                  ref={(r) => {
                    geoLayerRef.current = r as unknown as LeafletGeoJSON | null;
                  }}
                />
                {showUndervalued && (
                  <MarkerClusterGroup chunkedLoading iconCreateFunction={clusterIcon} showCoverageOnHover={false} maxClusterRadius={50}>
                    {undervaluedPoints.map(({ o, lat, lon }) => {
                      const dev = o.evaluation?.deviation_pct ?? 0;
                      return (
                        <Marker key={o.id} position={[lat, lon]} icon={undervaluedIcon(dev)}>
                          <Popup>
                            <div className="text-xs space-y-1">
                              <div className="font-semibold">
                                {(o.listing?.rooms ?? '?')}-комн., {formatNumber(o.listing?.area ?? 0)} м²
                              </div>
                              <div>Цена: {formatNumber(o.listing?.price ?? 0)} ₽</div>
                              <div>
                                Прогноз: {formatNumber(o.evaluation?.predicted_price ?? 0)} ₽ (
                                <span className="text-red-600">{dev.toFixed(1)}%</span>)
                              </div>
                              <div className="flex flex-wrap gap-2 pt-1">
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  className="h-7 px-2 text-xs"
                                  onClick={() => navigate(`/objects?focus=${o.id}`)}
                                >
                                  Открыть в Объектах <ArrowRight className="ml-1 h-3 w-3" />
                                </Button>
                                {o.url && (
                                  <a
                                    href={o.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-primary underline self-center"
                                  >
                                    Объявление
                                  </a>
                                )}
                              </div>
                            </div>
                          </Popup>
                        </Marker>
                      );
                    })}
                  </MarkerClusterGroup>
                )}
                <FlyTo target={flyTarget} />
              </MapContainer>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            {mode === 'price' && priceRange.max > 0 && (
              <div className="flex flex-1 items-center gap-3">
                <span>{formatNumber(priceRange.min)} ₽/м²</span>
                <div
                  className="h-2 flex-1 rounded-full"
                  style={{ background: 'linear-gradient(to right, hsl(262, 70%, 70%), hsl(262, 70%, 35%))' }}
                />
                <span>{formatNumber(priceRange.max)} ₽/м²</span>
              </div>
            )}
            {mode === 'sentiment' && (
              <div className="flex flex-1 items-center gap-3">
                <span>−1 негатив</span>
                <div
                  className="h-2 flex-1 rounded-full"
                  style={{ background: 'linear-gradient(to right, hsl(0, 65%, 55%), hsl(60, 65%, 55%), hsl(120, 65%, 55%))' }}
                />
                <span>+1 позитив</span>
              </div>
            )}
            {showUndervalued && (
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-full bg-red-500" />
                Недооценённые ({undervaluedPoints.length})
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
