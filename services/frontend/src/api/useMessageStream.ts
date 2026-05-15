import { useEffect, useRef } from 'react';
import { getStoredToken, API_BASE } from '@/api/client';
import type { Message } from '@/api/types';

export function useMessageStream(enabled: boolean, onMessage: (msg: Message) => void) {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    const token = getStoredToken();
    const url = new URL(`${API_BASE}/messages/stream`, window.location.origin);
    if (token) url.searchParams.set('token', token);

    const es = new EventSource(url.toString());

    const handle = (e: MessageEvent<string>) => {
      try {
        const data = JSON.parse(e.data) as Message;
        if (data && data.id) onMessageRef.current(data);
      } catch (err) {
        console.warn('SSE parse error', err);
      }
    };
    es.addEventListener('message', handle);

    return () => {
      es.removeEventListener('message', handle);
      es.close();
    };
  }, [enabled]);
}
