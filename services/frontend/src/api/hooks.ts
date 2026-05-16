import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { User } from '@/api/types';
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
  Favorite,
  Subscription,
  TrendsLatest,
} from '@/api/types';

export interface DateRange {
  from?: Date;
  to?: Date;
}

export function rangeWindow(range?: DateRange): { since: string; until: string } {
  if (range?.from || range?.to) {
    const until = range.to ?? new Date();
    const since = range.from ?? new Date(until.getTime() - 180 * 86_400_000);
    return { since: since.toISOString(), until: until.toISOString() };
  }
  return dashboardWindow();
}

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

export function useObject(id: string | undefined) {
  return useQuery({
    queryKey: ['object', id],
    enabled: Boolean(id),
    queryFn: async () => {
      const res = await api.get<RealEstateObject>(`/objects/${id}`);
      return res.data;
    },
  });
}

export function useFavorites(target_kind?: 'message' | 'object') {
  return useQuery({
    queryKey: ['favorites', target_kind ?? 'all'],
    queryFn: async () => {
      const res = await api.get<Favorite[]>('/favorites', {
        params: target_kind ? { target_kind } : undefined,
      });
      return res.data;
    },
  });
}

export function useAddFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { target_kind: 'message' | 'object'; target_ref: string }) =>
      (await api.post<Favorite>('/favorites', data)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['favorites'] }),
  });
}

export function useRemoveFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { target_kind: 'message' | 'object'; target_ref: string }) => {
      await api.delete('/favorites', { data });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['favorites'] }),
  });
}

export function useSubscriptions() {
  return useQuery({
    queryKey: ['subscriptions'],
    queryFn: async () => (await api.get<Subscription[]>('/subscriptions')).data,
  });
}

export function useCreateSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { target_kind: 'source' | 'topic' | 'object'; target_ref: string; notify?: boolean }) =>
      (await api.post<Subscription>('/subscriptions', { notify: false, ...data })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions'] }),
  });
}

export function useDeleteSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/subscriptions/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions'] }),
  });
}

export function useUpdateProfile() {
  return useMutation({
    mutationFn: async (data: { email?: string; display_name?: string }) =>
      (await api.patch<User>('/auth/me', data)).data,
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (data: { current_password: string; new_password: string }) => {
      await api.post('/auth/change-password', data);
    },
  });
}

export function useTrendsLatest() {
  return useQuery({
    queryKey: ['trends', 'latest'],
    retry: false,
    queryFn: async (): Promise<TrendsLatest | null> => {
      try {
        return (await api.get<TrendsLatest>('/trends/latest')).data;
      } catch {
        return null;
      }
    },
  });
}

export function useRecomputeTrends() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<TrendsLatest>('/trends/recompute')).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trends'] }),
  });
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

export function safeQuery<T>(path: string, params?: Record<string, unknown>) {
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

export function dashboardWindow(): { since: string; until: string } {
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

export function useOverview(range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'overview', range],
    queryFn: async (): Promise<OverviewKpi | null> => {
      const raw = await safeQuery<OverviewResponse>('/dashboards/overview', rangeWindow(range))();
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

export function useTopicsActivity(topic: string, granularity: 'hour' | 'day' = 'hour', range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'topics', topic, granularity, range],
    enabled: Boolean(topic),
    queryFn: async (): Promise<TimeSeries | null> => {
      const raw = await safeQuery<PointsEnvelope<BucketPoint>>('/dashboards/topics/activity', {
        topic,
        granularity,
        ...rangeWindow(range),
      })();
      return aggregateByBucket(raw?.points, (p) => p.messages_total, 'sum');
    },
    retry: false,
  });
}

export function usePricesTimeseries(granularity: 'day' | 'week' | 'month' = 'month', range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'prices-ts', granularity, range],
    queryFn: async (): Promise<TimeSeries | null> => {
      const raw = await safeQuery<PointsEnvelope<BucketPoint>>('/dashboards/prices/timeseries', {
        granularity,
        ...rangeWindow(range),
      })();
      return aggregateByBucket(raw?.points, (p) => p.avg_price_per_m2, 'avg');
    },
    retry: false,
  });
}

export function useSentimentByDistrict(range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'sentiment-by-district', range],
    queryFn: async (): Promise<DistrictSentiment[] | null> => {
      const raw = await safeQuery<PointsEnvelope<DistrictSentiment>>(
        '/dashboards/sentiment/by-district',
        rangeWindow(range)
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

export function useListingsByChannel(range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'listings-by-channel', range],
    queryFn: async (): Promise<ChannelDistribution[] | null> => {
      const raw = await safeQuery<PointsEnvelope<ListingsByChannelPoint>>(
        '/dashboards/listings/by-channel',
        rangeWindow(range)
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

export interface PriceDistributionPoint {
  rooms: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  listings: number;
}

export function usePriceDistribution() {
  return useQuery({
    queryKey: ['dashboard', 'price-distribution'],
    queryFn: async (): Promise<PriceDistributionPoint[] | null> => {
      const raw = await safeQuery<PointsEnvelope<PriceDistributionPoint>>(
        '/dashboards/prices/distribution'
      )();
      return raw?.points ?? [];
    },
    retry: false,
  });
}

export interface TopicCooccurrencePoint {
  topic_a: string;
  topic_b: string;
  weight: number;
}

export function useTopicCooccurrence(limit = 12, range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'topic-cooccurrence', limit, range],
    queryFn: async (): Promise<TopicCooccurrencePoint[] | null> => {
      const raw = await safeQuery<PointsEnvelope<TopicCooccurrencePoint>>(
        '/dashboards/topics/cooccurrence',
        { ...rangeWindow(range), limit }
      )();
      return raw?.points ?? [];
    },
    retry: false,
  });
}

export interface UndervaluedSharePoint {
  day: string;
  undervalued: number;
  listings_total: number;
  share: number;
}

export function useUndervaluedShare(range?: DateRange) {
  return useQuery({
    queryKey: ['dashboard', 'undervalued-share', range],
    queryFn: async (): Promise<UndervaluedSharePoint[] | null> => {
      const raw = await safeQuery<PointsEnvelope<UndervaluedSharePoint>>(
        '/dashboards/model-quality/undervalued-share',
        rangeWindow(range)
      )();
      return raw?.points ?? [];
    },
    retry: false,
  });
}
