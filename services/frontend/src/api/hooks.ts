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

export function useOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: safeQuery<OverviewKpi>('/dashboards/overview'),
    retry: false,
  });
}

export function useTopicsActivity(topic: string, granularity: 'hour' | 'day' = 'hour') {
  return useQuery({
    queryKey: ['dashboard', 'topics', topic, granularity],
    enabled: Boolean(topic),
    queryFn: safeQuery<TimeSeries>('/dashboards/topics/activity', { topic, granularity }),
    retry: false,
  });
}

export function usePricesTimeseries(granularity: 'day' | 'week' | 'month' = 'month') {
  return useQuery({
    queryKey: ['dashboard', 'prices-ts', granularity],
    queryFn: safeQuery<TimeSeries>('/dashboards/prices/timeseries', { granularity }),
    retry: false,
  });
}

export function useSentimentByDistrict() {
  return useQuery({
    queryKey: ['dashboard', 'sentiment-by-district'],
    queryFn: safeQuery<DistrictSentiment[]>('/dashboards/sentiment/by-district'),
    retry: false,
  });
}

export function useListingsByChannel() {
  return useQuery({
    queryKey: ['dashboard', 'listings-by-channel'],
    queryFn: safeQuery<ChannelDistribution[]>('/dashboards/listings/by-channel'),
    retry: false,
  });
}

export function useModelQuality() {
  return useQuery({
    queryKey: ['dashboard', 'model-quality'],
    queryFn: safeQuery<TimeSeries>('/dashboards/model-quality'),
    retry: false,
  });
}

export function usePricesByDistrict() {
  return useQuery({
    queryKey: ['dashboard', 'prices-by-district'],
    queryFn: safeQuery<DistrictPrice[]>('/dashboards/prices/by-district'),
    retry: false,
  });
}
