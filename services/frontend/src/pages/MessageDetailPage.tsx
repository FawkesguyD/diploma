import { Link, useParams } from 'react-router-dom';
import { useMessage } from '@/api/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { formatDateTime } from '@/lib/utils';

export function MessageDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, isError } = useMessage(id);

  return (
    <div className="space-y-6">
      <Button variant="ghost" asChild>
        <Link to="/messages">
          <ArrowLeft className="h-4 w-4" />
          Назад к ленте
        </Link>
      </Button>

      {isPending && <Skeleton className="h-96 w-full" />}
      {isError && (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground">Не удалось загрузить сообщение.</p>
        </Card>
      )}

      {data && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">{data.channel_kind}</Badge>
                <span className="font-medium text-foreground">
                  {data.author?.name || data.author?.handle || data.channel_site}
                </span>
                <span>•</span>
                <time>{formatDateTime(data.published_at)}</time>
                {data.lang && <Badge variant="muted">{data.lang}</Badge>}
              </div>
              <CardTitle className="text-base font-normal leading-relaxed">
                <p className="whitespace-pre-wrap">{data.text}</p>
              </CardTitle>
            </CardHeader>
            {data.url && (
              <CardContent>
                <a
                  href={data.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                >
                  Открыть источник <ExternalLink className="h-3 w-3" />
                </a>
              </CardContent>
            )}
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Аннотация</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {data.annotation?.sentiment && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Тональность</span>
                    <Badge variant="muted">{data.annotation.sentiment.label}</Badge>
                  </div>
                )}
                {data.annotation?.is_ad !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Реклама</span>
                    <Badge variant={data.annotation.is_ad ? 'warning' : 'muted'}>
                      {data.annotation.is_ad ? 'да' : 'нет'}
                    </Badge>
                  </div>
                )}
                {data.annotation?.topics && data.annotation.topics.length > 0 && (
                  <div>
                    <div className="mb-1 text-muted-foreground">Темы</div>
                    <div className="flex flex-wrap gap-1">
                      {data.annotation.topics.map((t) => (
                        <Badge key={t.slug} variant="secondary" className="font-mono text-[10px]">
                          {t.slug} · {t.score.toFixed(2)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {data.annotation?.entities && data.annotation.entities.length > 0 && (
                  <div>
                    <div className="mb-1 text-muted-foreground">Сущности</div>
                    <div className="flex flex-wrap gap-1">
                      {data.annotation.entities.map((e, i) => (
                        <Badge key={i} variant="outline">
                          {(e.text ?? e.value ?? '') as string} {e.type ? `· ${e.type}` : ''}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {data.raw_meta && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">raw_meta</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-auto rounded-md bg-muted/40 p-3 text-xs">
                    {JSON.stringify(data.raw_meta, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
