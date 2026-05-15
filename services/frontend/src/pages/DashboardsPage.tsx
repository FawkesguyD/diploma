import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  useListingsByChannel,
  useModelQuality,
  useOverview,
  usePricesTimeseries,
  useSentimentByDistrict,
  useTopicsActivity,
} from '@/api/hooks';
import { Activity, AlertTriangle, BarChart3, Building2, Database, MessageSquare } from 'lucide-react';
import { formatNumber } from '@/lib/utils';

const CHART_COLORS = [
  'hsl(262, 80%, 55%)',
  'hsl(199, 80%, 50%)',
  'hsl(152, 65%, 45%)',
  'hsl(35, 90%, 55%)',
  'hsl(348, 75%, 55%)',
  'hsl(280, 60%, 60%)',
];

export function DashboardsPage() {
  const overview = useOverview();
  const [topic, setTopic] = useState('mortgage_rates');
  const [granularity, setGranularity] = useState<'hour' | 'day'>('day');
  const topics = useTopicsActivity(topic, granularity);
  const [priceGran, setPriceGran] = useState<'day' | 'week' | 'month'>('month');
  const prices = usePricesTimeseries(priceGran);
  const sentiment = useSentimentByDistrict();
  const channels = useListingsByChannel();
  const quality = useModelQuality();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Аналитические дашборды</h1>
        <p className="text-sm text-muted-foreground">
          Сводные метрики по информационным потокам, рынку недвижимости и качеству моделей
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={<MessageSquare className="h-4 w-4" />}
          label="Сообщений всего"
          value={overview.data?.messages_total}
          loading={overview.isPending}
        />
        <KpiCard
          icon={<Activity className="h-4 w-4" />}
          label="За 24 часа"
          value={overview.data?.messages_24h}
          loading={overview.isPending}
        />
        <KpiCard
          icon={<Building2 className="h-4 w-4" />}
          label="Объектов"
          value={overview.data?.objects_total}
          loading={overview.isPending}
        />
        <KpiCard
          icon={<Database className="h-4 w-4" />}
          label="Активных источников"
          value={overview.data?.active_sources}
          loading={overview.isPending}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Активность по теме"
          description="Кол-во сообщений по теме во времени"
          loading={topics.isFetching}
          empty={!topics.data || topics.data.series.length === 0}
          controls={
            <div className="flex gap-2">
              <Input
                className="h-8 w-40"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="topic_slug"
              />
              <Select value={granularity} onValueChange={(v) => setGranularity(v as 'hour' | 'day')}>
                <SelectTrigger className="h-8 w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hour">Час</SelectItem>
                  <SelectItem value="day">День</SelectItem>
                </SelectContent>
              </Select>
            </div>
          }
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={topics.data?.series ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="t" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5, 16)} />
              <YAxis tick={{ fontSize: 10 }} />
              <ChartTooltip
                contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))' }}
              />
              <Line type="monotone" dataKey="v" stroke={CHART_COLORS[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Динамика цен ₽/м²"
          description="Среднее значение цены за квадратный метр"
          loading={prices.isFetching}
          empty={!prices.data || prices.data.series.length === 0}
          controls={
            <Select value={priceGran} onValueChange={(v) => setPriceGran(v as 'day' | 'week' | 'month')}>
              <SelectTrigger className="h-8 w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="day">День</SelectItem>
                <SelectItem value="week">Неделя</SelectItem>
                <SelectItem value="month">Месяц</SelectItem>
              </SelectContent>
            </Select>
          }
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={prices.data?.series ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="t" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(0, 10)} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => formatNumber(v)} />
              <ChartTooltip
                formatter={(v: number) => formatNumber(v)}
                contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))' }}
              />
              <Line type="monotone" dataKey="v" stroke={CHART_COLORS[1]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Тональность по районам"
          description="Среднее значение sentiment по районам"
          loading={sentiment.isFetching}
          empty={!sentiment.data || sentiment.data.length === 0}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={sentiment.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="district_slug" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 10 }} />
              <ChartTooltip
                contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))' }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="pos_count" name="Позитив" fill="hsl(152, 65%, 45%)" />
              <Bar dataKey="neu_count" name="Нейтрально" fill="hsl(215, 16%, 60%)" />
              <Bar dataKey="neg_count" name="Негатив" fill="hsl(348, 75%, 55%)" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Объявления по каналам"
          description="Распределение источников"
          loading={channels.isFetching}
          empty={!channels.data || channels.data.length === 0}
        >
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={channels.data ?? []}
                dataKey="count"
                nameKey={(channels.data && channels.data[0]?.channel_kind ? 'channel_kind' : 'channel') as string}
                outerRadius={100}
                label
              >
                {(channels.data ?? []).map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <ChartTooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Качество модели"
          description="MAE / отклонения по времени"
          loading={quality.isFetching}
          empty={!quality.data || quality.data.series.length === 0}
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={quality.data?.series ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="t" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(0, 10)} />
              <YAxis tick={{ fontSize: 10 }} />
              <ChartTooltip
                contentStyle={{ backgroundColor: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))' }}
              />
              <Line type="monotone" dataKey="v" stroke={CHART_COLORS[3]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}

function KpiCard({
  icon,
  label,
  value,
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string | undefined;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between text-muted-foreground">
          <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
          <span className="text-primary">{icon}</span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-24" />
        ) : (
          <div className="mt-2 text-3xl font-semibold tracking-tight">
            {value === undefined ? '—' : typeof value === 'number' ? formatNumber(value) : value}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChartCard({
  title,
  description,
  controls,
  children,
  loading,
  empty,
  className,
}: {
  title: string;
  description?: string;
  controls?: React.ReactNode;
  children: React.ReactNode;
  loading: boolean;
  empty: boolean;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <BarChart3 className="h-4 w-4 text-primary" /> {title}
          </CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {controls}
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : empty ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <AlertTriangle className="h-6 w-6" />
            <span className="text-sm">Нет данных или метрика недоступна</span>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
