export type Role = 'user' | 'admin';

export interface User {
  id: string;
  email: string;
  display_name?: string | null;
  role: Role;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export type SourceKind = 'tg' | 'news' | 'rss' | 'html' | 'realestate_site';

export interface Source {
  id: string;
  kind: SourceKind;
  name: string;
  url_or_handle: string;
  enabled: boolean;
  poll_interval_sec: number;
  config?: Record<string, unknown>;
  last_polled_at: string | null;
}

export interface SourceCreate {
  kind: SourceKind;
  name: string;
  url_or_handle: string;
  poll_interval_sec?: number;
  config?: Record<string, unknown>;
}

export interface SourcePatch {
  name?: string;
  enabled?: boolean;
  poll_interval_sec?: number;
  config?: Record<string, unknown>;
}

export type SentimentLabel = 'positive' | 'neutral' | 'negative';
export type ChannelKind = 'tg' | 'news' | 'rss' | 'html';

export interface MessageAuthor {
  name?: string;
  handle?: string;
  url?: string;
}

export interface TopicScore {
  slug: string;
  score: number;
}

export interface Sentiment {
  label: SentimentLabel;
  score: number;
}

export interface MessageEntity {
  text?: string;
  type?: string;
  value?: string;
}

export interface MessageAnnotation {
  is_ad?: boolean;
  ad_score?: number;
  topics?: TopicScore[];
  sentiment?: Sentiment;
  entities?: MessageEntity[];
  summary?: string | null;
  lang?: string;
}

export interface Message {
  id: string;
  external_id?: string;
  source_id: string;
  channel_kind: ChannelKind;
  channel_site: string;
  url?: string | null;
  author?: MessageAuthor;
  published_at: string;
  fetched_at?: string;
  created_at?: string;
  updated_at?: string;
  text: string;
  lang?: string;
  media?: unknown[];
  raw_meta?: Record<string, unknown>;
  annotation?: MessageAnnotation | null;
}

export interface CursorPage<T> {
  items: T[];
  next_cursor?: string | null;
}

export interface OffsetPage<T> {
  items: T[];
  total?: number;
  skip?: number;
  limit?: number;
}

export interface ObjectListing {
  title?: string;
  city?: string;
  district?: string;
  address?: string;
  price?: number;
  price_per_m2?: number;
  area?: number;
  rooms?: number;
  floor?: number;
  total_floors?: number;
  description?: string;
  photos?: string[];
  geo?: { lat?: number; lon?: number };
  [k: string]: unknown;
}

export interface ObjectEvaluation {
  model_version?: string;
  predicted_price?: number;
  deviation_abs?: number;
  deviation_pct?: number;
  is_undervalued?: boolean;
  rank_in_run?: number;
  computed_at?: string;
}

export interface RealEstateObject {
  id: string;
  source_id: string;
  object_kind: string;
  channel_site: string;
  url: string;
  published_at: string;
  listing: ObjectListing;
  status: string;
  evaluation?: ObjectEvaluation | null;
}

export interface JobAccepted {
  job_id: string;
  status_url?: string;
}

export type JobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'completed';

export interface Job {
  id: string;
  kind?: string;
  status: JobStatus;
  started_at?: string | null;
  finished_at?: string | null;
  progress?: number | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface TimePoint {
  t: string;
  v: number;
}

export interface TimeSeries {
  granularity?: string;
  series: TimePoint[];
}

export interface DistrictSentiment {
  district_slug: string;
  messages_total: number;
  pos_count: number;
  neu_count: number;
  neg_count: number;
  sentiment_avg: number;
}

export interface DistrictPrice {
  district_slug: string;
  avg_price?: number;
  avg_price_per_m2?: number;
  count?: number;
}

export interface ChannelDistribution {
  channel_kind?: string;
  channel?: string;
  count: number;
}

export interface Favorite {
  id: string;
  target_kind: 'message' | 'object';
  target_ref: string;
  created_at: string;
}

export interface Subscription {
  id: string;
  target_kind: 'source' | 'topic' | 'object';
  target_ref: string;
  notify: boolean;
  created_at: string;
}

export interface Trend {
  slug: string;
  title: string;
  mentions: number;
  delta_pct: number | null;
  summary: string;
  sample_ids: string[];
}

export interface TrendsLatest {
  computed_at: string;
  period_start: string;
  period_end: string;
  items: Trend[];
}

export interface OverviewKpi {
  messages_total?: number;
  messages_24h?: number;
  objects_total?: number;
  undervalued_count?: number;
  active_sources?: number;
  [k: string]: number | string | undefined;
}
