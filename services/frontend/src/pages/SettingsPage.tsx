import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth/AuthProvider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Bell, KeyRound, LogOut, UserCog } from 'lucide-react';
import {
  useChangePassword,
  useCreateSubscription,
  useDeleteSubscription,
  useSources,
  useSubscriptions,
  useUpdateProfile,
} from '@/api/hooks';
import { extractErrorMessage } from '@/api/client';

export function SettingsPage() {
  const { user, logout } = useAuth();
  const sources = useSources();
  const subs = useSubscriptions();
  const create = useCreateSubscription();
  const del = useDeleteSubscription();

  const sourceSubs = (subs.data ?? []).filter((s) => s.target_kind === 'source');
  const isSubbed = (sourceId: string) => sourceSubs.find((s) => s.target_ref === sourceId);

  async function toggleSub(sourceId: string, on: boolean) {
    try {
      if (on) {
        await create.mutateAsync({ target_kind: 'source', target_ref: sourceId, notify: false });
        toast.success('Подписка добавлена');
      } else {
        const sub = isSubbed(sourceId);
        if (sub) {
          await del.mutateAsync(sub.id);
          toast.success('Подписка удалена');
        }
      }
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  async function toggleNotify(sourceId: string, notify: boolean) {
    try {
      const sub = isSubbed(sourceId);
      if (!sub) return;
      await del.mutateAsync(sub.id);
      await create.mutateAsync({ target_kind: 'source', target_ref: sourceId, notify });
      toast.success(notify ? 'Уведомления включены' : 'Уведомления выключены');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Настройки</h1>
        <p className="text-sm text-muted-foreground">Профиль, безопасность и подписки</p>
      </div>

      <ProfileCard />
      <PasswordCard />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bell className="h-4 w-4 text-primary" /> Подписки на источники
          </CardTitle>
          <CardDescription>
            Подписывайтесь на источники, чтобы быстро находить их сообщения и получать уведомления
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sources.isPending || subs.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : (sources.data ?? []).length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Источников пока нет</p>
          ) : (
            <div className="space-y-2">
              {(sources.data ?? []).map((s) => {
                const sub = isSubbed(s.id);
                return (
                  <div key={s.id} className="flex items-center justify-between rounded-md border p-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {s.kind}
                        </Badge>
                        {!s.enabled && <Badge variant="muted">выключен</Badge>}
                      </div>
                      <div className="truncate font-mono text-xs text-muted-foreground">
                        {s.url_or_handle}
                      </div>
                    </div>
                    <div className="flex items-center gap-6 pl-4">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">подписка</span>
                        <Switch
                          checked={Boolean(sub)}
                          onCheckedChange={(on) => toggleSub(s.id, on)}
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">уведомления</span>
                        <Switch
                          checked={sub?.notify ?? false}
                          disabled={!sub}
                          onCheckedChange={(on) => toggleNotify(s.id, on)}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex items-center justify-between p-4">
          <div>
            <div className="text-sm font-medium">Завершить сессию</div>
            <div className="text-xs text-muted-foreground">Выйти из учётной записи на этом устройстве</div>
          </div>
          <Button variant="outline" onClick={logout}>
            <LogOut className="h-4 w-4" /> Выйти
          </Button>
        </CardContent>
      </Card>

      {!user && <Skeleton className="h-12 w-full" />}
    </div>
  );
}

function ProfileCard() {
  const { user, setUser } = useAuth();
  const update = useUpdateProfile();
  const [email, setEmail] = useState(user?.email ?? '');
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');

  if (!user) return <Skeleton className="h-40 w-full" />;

  const dirty = email.trim() !== user.email || (displayName ?? '') !== (user.display_name ?? '');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!user || !dirty) return;
    try {
      const patch: { email?: string; display_name?: string } = {};
      if (email.trim() !== user.email) patch.email = email.trim();
      if ((displayName ?? '') !== (user.display_name ?? '')) patch.display_name = displayName.trim() || '';
      const updated = await update.mutateAsync(patch);
      setUser(updated);
      toast.success('Профиль обновлён');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserCog className="h-4 w-4 text-primary" /> Профиль
        </CardTitle>
        <CardDescription>Email и отображаемое имя</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-xs">Email</Label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Имя</Label>
            <Input
              value={displayName ?? ''}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Как к вам обращаться"
              autoComplete="name"
            />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={!dirty || update.isPending}>
              {update.isPending ? 'Сохраняем…' : 'Сохранить'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const change = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (next.length < 6) {
      toast.error('Новый пароль — минимум 6 символов');
      return;
    }
    if (next !== confirm) {
      toast.error('Пароли не совпадают');
      return;
    }
    try {
      await change.mutateAsync({ current_password: current, new_password: next });
      toast.success('Пароль изменён');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4 text-primary" /> Смена пароля
        </CardTitle>
        <CardDescription>Минимум 6 символов</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label className="text-xs">Текущий пароль</Label>
            <Input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Новый пароль</Label>
            <Input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Подтверждение</Label>
            <Input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
          </div>
          <div className="sm:col-span-3">
            <Button type="submit" disabled={change.isPending || !current || !next || !confirm}>
              {change.isPending ? 'Меняем…' : 'Сменить пароль'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
