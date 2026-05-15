import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type {
  CursorPage,
  Job,
  JobAccepted,
  Message,
  RealEstateObject,
  Source,
  SourceCreate,
  SourcePatch,
  TimeSeries,
  DistrictSentiment,
  DistrictPrice,
  ChannelDistribution,
  OverviewKpi,
} from '@/api/types';

export interface MessageFilters {
  topic?: string;
  district?: string;
  sentiment?: string;
  channel_kind?: string;
  source_id?: string;
  is_ad?: boolean;
  since?: string;
  until?: string;
}

export function useMessagesInfinite(filters: MessageFilters) {
  return useInfiniteQuery({
    queryKey: ['messages', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string | number | boolean | undefined> = { ...filters, limit: 30 };
      if (pageParam) params.cursor = pageParam;
      Object.keys(params).forEach((k) => {
        const v = params[k];
        if (v === undefined || v === '' || v === null) delete params[k];
      });
      const res = await api.get<CursorPage<Message>>('/messages', { params });
      return res.data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useMessage(id: string | undefined) {
  return useQuery({
    queryKey: ['message', id],
    enabled: Boolean(id),
    queryFn: async () => {
      const res = await api.get<Message>(`/messages/${id}`);
      return res.data;
    },
  });
}

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: async () => {
      const res = await api.get<Source[]>('/sources');
      return res.data;
    },
  });
}

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: SourceCreate) => (await api.post<Source>('/sources', data)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  });
}

export function usePatchSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: SourcePatch }) =>
      (await api.patch<Source>(`/sources/${id}`, data)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/sources/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  });
}

export function useParseSource() {
  return useMutation({
    mutationFn: async (id: string) => (await api.post<JobAccepted>(`/sources/${id}/parse`)).data,
  });
}

export function useJob(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['job', id],
    enabled: Boolean(id) && enabled,
    refetchInterval: (q) => {
      const data = q.state.data as Job | undefined;
      if (!data) return 1500;
      if (data.status === 'succeeded' || data.status === 'failed' || data.status === 'completed') return false;
      return 1500;
    },
    queryFn: async () => (await api.get<Job>(`/jobs/${id}`)).data,
  });
}

export interface ObjectFilters {
  city?: string;
  district?: string;
  rooms?: number;
  price_min?: number;
  price_max?: number;
  area_min?: number;
  area_max?: number;
  is_undervalued?: boolean;
  object_kind?: string;
}

export function useObjects(filters: ObjectFilters) {
  return useQuery({
    queryKey: ['objects', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = { ...filters, limit: 50 };
      Object.keys(params).forEach((k) => {
        const v = params[k];
        if (v === undefined || v === '' || v === null) delete params[k];
      });
      const res = await api.get<{ items: RealEstateObject[]; next_cursor?: string | null; total?: number }>(
        '/objects',
        { params }
      );
      return res.data;
    },
  });
}

export function useTopUndervalued(filters: { city?: string; district?: string; limit?: number }) {
  return useQuery({
    queryKey: ['top-undervalued', filters],
    queryFn: async () => {
      const params: Record<string, unknown> = { limit: 20, ...filters };
      Object.keys(params).forEach((k) => {
        const v = params[k];
        if (v === undefined || v === '') delete params[k];
      });
      const res = await api.get<RealEstateObject[] | { items: RealEstateObject[] }>('/objects/top-undervalued', {
        params,
      });
      const data = res.data;
      return Array.isArray(data) ? data : data.items;
    },
  });
}

function safeQuery<T>(path: string, params?: Record<string, unknown>) {
  return async (): Promise<T | null> => {
    try {
      const res = await api.get<T>(path, { params });
      return res.data;
    } catch {
      return null;
    }
  };
}

const DASHBOARD_WINDOW_DAYS = 180;

function dashboardWindow(): { since: string; until: string } {
  const until = new Date();
  const since = new Date(until.getTime() - DASHBOARD_WINDOW_DAYS * 86_400_000);
  return { since: since.toISOString(), until: until.toISOString() };
}

interface OverviewResponse {
  kpi?: {
    listings_new?: number;
    undervalued?: number;
    messages_non_ad?: number;
    sentiment_avg?: number | null;
  } | null;
}

export function useOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: async (): Promise<OverviewKpi | null> => {
      const raw = await safeQuery<OverviewResponse>('/dashboards/overview', dashboardWindow())();
      if (!raw?.kpi) return null;
      const k = raw.kpi;
      return {
        messages_total: k.messages_non_ad,
        objects_total: k.listings_new,
        undervalued_count: k.undervalued,
        active_sources: k.sentiment_avg ?? undefined,
      } as OverviewKpi;
    },
    retry: false,
  });
}

interface BucketPoint {
  bucket?: string;
  day?: string;
  messages_total?: number;
  avg_price_per_m2?: number;
  mae_pct?: number;
}
interface PointsEnvelope<P> {
  points: P[];
}

function aggregateByBucket<P extends BucketPoint>(
  points: P[] | undefined,
  pick: (p: P) => number | undefined,
  agg: 'sum' | 'avg' = 'sum'
): TimeSeries {
  if (!points?.length) return { series: [] };
  const acc = new Map<string, { sum: number; n: number }>();
  for (const p of points) {
    const t = p.bucket ?? p.day;
    const v = pick(p);
    if (!t || v === undefined || v === null) continue;
    const cur = acc.get(t) ?? { sum: 0, n: 0 };
    cur.sum += v;
    cur.n += 1;
    acc.set(t, cur);
  }
  const series = Array.from(acc.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([t, { sum, n }]) => ({ t, v: agg === 'avg' ? sum / n : sum }));
  return { series };
}

export function useTopicsActivity(topic: string, granularity: 'hour' | 'day' = 'hour') {
  return useQuery({
    queryKey: ['dashboard', 'topics', topic, granularity],
    enabled: Boolean(topic),
    queryFn: async (): Promise<TimeSeries | null> => {
      const raw = await safeQuery<PointsEnvelope<BucketPoint>>('/dashboards/topics/activity', {
        topic,
        granularity,
        ...dashboardWindow(),
      })();
      return aggregateByBucket(raw?.points, (p) => p.messages_total, 'sum');
    },
    retry: false,
  });
}

export function usePricesTimeseries(granularity: 'day' | 'week' | 'month' = 'month') {
  return useQuery({
    queryKey: ['dashboard', 'prices-ts', granularity],
    queryFn: async (): Promise<TimeSeries | null> => {
      const raw = await safeQuery<PointsEnvelope<BucketPoint>>('/dashboards/prices/timeseries', {
        granularity,
        ...dashboardWindow(),
      })();
      return aggregateByBucket(raw?.points, (p) => p.avg_price_per_m2, 'avg');
    },
    retry: false,
  });
}

export function useSentimentByDistrict() {
  return useQuery({
    queryKey: ['dashboard', 'sentiment-by-district'],
    queryFn: async (): Promise<DistrictSentiment[] | null> => {
      const raw = await safeQuery<PointsEnvelope<DistrictSentiment>>(
        '/dashboards/sentiment/by-district',
        dashboardWindow()
      )();
      return raw?.points ?? [];
    },
    retry: false,
  });
}

interface ListingsByChannelPoint {
  channel_site?: string;
  channel_kind?: string;
  listings_new?: number;
}

export function useListingsByChannel() {
  return useQuery({
    queryKey: ['dashboard', 'listings-by-channel'],
    queryFn: async (): Promise<ChannelDistribution[] | null> => {
      const raw = await safeQuery<PointsEnvelope<ListingsByChannelPoint>>(
        '/dashboards/listings/by-channel',
        dashboardWindow()
      )();
      const acc = new Map<string, number>();
      for (const p of raw?.points ?? []) {
        const key = p.channel_site ?? p.channel_kind ?? 'unknown';
        acc.set(key, (acc.get(key) ?? 0) + (p.listings_new ?? 0));
      }
      return Array.from(acc.entries()).map(([channel, count]) => ({ channel, count }));
    },
    retry: false,
  });
}

export function useModelQuality() {
  return useQuery({
    queryKey: ['dashboard', 'model-quality'],
    queryFn: async (): Promise<TimeSeries | null> => {
      const raw = await safeQuery<PointsEnvelope<BucketPoint>>(
        '/dashboards/model-quality',
        dashboardWindow()
      )();
      return aggregateByBucket(raw?.points, (p) => p.mae_pct, 'avg');
    },
    retry: false,
  });
}

interface PricesByDistrictPoint {
  district_slug: string;
  avg_price_per_m2: number;
  listings: number;
}

export function usePricesByDistrict() {
  return useQuery({
    queryKey: ['dashboard', 'prices-by-district'],
    queryFn: async (): Promise<DistrictPrice[] | null> => {
      const raw = await safeQuery<PointsEnvelope<PricesByDistrictPoint>>(
        '/dashboards/prices/by-district'
      )();
      return (raw?.points ?? []).map((p) => ({
        district_slug: p.district_slug,
        avg_price_per_m2: p.avg_price_per_m2,
        count: p.listings,
      }));
    },
    retry: false,
  });
}
