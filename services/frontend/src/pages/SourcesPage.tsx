import { useState } from 'react';
import { toast } from 'sonner';
import {
  useCreateSource,
  useDeleteSource,
  useJob,
  useParseSource,
  usePatchSource,
  useSources,
} from '@/api/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Database, LoaderCircle, Plus, RefreshCcw, Trash2 } from 'lucide-react';
import { extractErrorMessage } from '@/api/client';
import { formatDateTime } from '@/lib/utils';
import type { SourceKind } from '@/api/types';

const KIND_LABEL: Record<SourceKind, string> = {
  tg: 'Telegram',
  rss: 'RSS',
  news: 'Новости',
  html: 'HTML',
  realestate_site: 'Площадка недвижимости',
};

export function SourcesPage() {
  const sources = useSources();
  const create = useCreateSource();
  const patch = usePatchSource();
  const del = useDeleteSource();
  const parse = useParseSource();

  const [activeJobId, setActiveJobId] = useState<string | undefined>(undefined);
  const job = useJob(activeJobId, Boolean(activeJobId));

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<{ kind: SourceKind; name: string; url_or_handle: string; poll: number }>({
    kind: 'rss',
    name: '',
    url_or_handle: '',
    poll: 300,
  });

  if (job.data && activeJobId) {
    const s = job.data.status;
    if (s === 'succeeded' || s === 'completed') {
      const items =
        (job.data.result as { items_collected?: number; collected?: number } | null)?.items_collected ??
        (job.data.result as { collected?: number } | null)?.collected;
      toast.success(`Парсинг завершён${items !== undefined ? ` · собрано: ${items}` : ''}`);
      setActiveJobId(undefined);
      void sources.refetch();
    } else if (s === 'failed') {
      toast.error(`Парсинг завершён с ошибкой: ${job.data.error ?? 'unknown'}`);
      setActiveJobId(undefined);
    }
  }

  async function handleCreate() {
    try {
      await create.mutateAsync({
        kind: form.kind,
        name: form.name,
        url_or_handle: form.url_or_handle,
        poll_interval_sec: form.poll,
      });
      toast.success('Источник создан');
      setCreateOpen(false);
      setForm({ kind: 'rss', name: '', url_or_handle: '', poll: 300 });
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  async function handleParse(id: string) {
    try {
      const res = await parse.mutateAsync(id);
      setActiveJobId(res.job_id);
      toast.message('Запущен парсинг', { description: `job_id: ${res.job_id}` });
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Источники</h1>
          <p className="text-sm text-muted-foreground">
            Telegram-каналы, RSS-фиды, площадки недвижимости — управление парсерами
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4" /> Добавить источник
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Новый источник</DialogTitle>
              <DialogDescription>
                Парсер начнёт опрос с указанным интервалом после создания
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Тип</Label>
                <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v as SourceKind })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(KIND_LABEL).map(([k, l]) => (
                      <SelectItem key={k} value={k}>
                        {l}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Название</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>URL / handle</Label>
                <Input
                  placeholder="https://… или @channel"
                  value={form.url_or_handle}
                  onChange={(e) => setForm({ ...form, url_or_handle: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Интервал опроса (сек)</Label>
                <Input
                  type="number"
                  min={30}
                  value={form.poll}
                  onChange={(e) => setForm({ ...form, poll: Number(e.target.value) || 300 })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>
                Отмена
              </Button>
              <Button onClick={handleCreate} disabled={create.isPending || !form.name || !form.url_or_handle}>
                {create.isPending && <LoaderCircle className="h-4 w-4 animate-spin" />}
                Создать
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Database className="h-4 w-4 text-primary" /> Список источников
          </CardTitle>
        </CardHeader>
        <CardContent>
          {sources.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : sources.data && sources.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Название</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>URL / handle</TableHead>
                  <TableHead>Последний опрос</TableHead>
                  <TableHead className="text-center">Активен</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.data.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-medium">{s.name}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{KIND_LABEL[s.kind] ?? s.kind}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{s.url_or_handle}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDateTime(s.last_polled_at)}</TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={s.enabled}
                        onCheckedChange={(checked) => {
                          patch
                            .mutateAsync({ id: s.id, data: { enabled: checked } })
                            .then(() => toast.success(checked ? 'Включён' : 'Выключен'))
                            .catch((err: unknown) => toast.error(extractErrorMessage(err)));
                        }}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={parse.isPending || activeJobId !== undefined}
                          onClick={() => handleParse(s.id)}
                        >
                          <RefreshCcw className="h-3.5 w-3.5" /> Парсить
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Удалить источник «${s.name}»?`)) {
                              del
                                .mutateAsync(s.id)
                                .then(() => toast.success('Удалён'))
                                .catch((err: unknown) => toast.error(extractErrorMessage(err)));
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">Нет источников</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
