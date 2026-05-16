import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '@/api/client';
import { dashboardWindow, rangeWindow, safeQuery } from './hooks';

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
  },
}));

describe('hooks helpers', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe('rangeWindow', () => {
    it('returns explicit from and until values unchanged', () => {
      const from = new Date('2026-05-01T00:00:00Z');
      const to = new Date('2026-05-10T00:00:00Z');
      expect(rangeWindow({ from, to })).toEqual({ since: from.toISOString(), until: to.toISOString() });
    });

    it('derives until from current time when only from is provided', () => {
      vi.useFakeTimers().setSystemTime(new Date('2026-05-16T12:00:00Z'));
      const from = new Date('2026-05-01T00:00:00Z');
      const result = rangeWindow({ from });
      expect(result.since).toBe(from.toISOString());
      expect(result.until).toBe('2026-05-16T12:00:00.000Z');
      vi.useRealTimers();
    });

    it('returns the dashboard window when range is undefined', () => {
      vi.useFakeTimers().setSystemTime(new Date('2026-05-16T12:00:00Z'));
      const result = rangeWindow();
      expect(result.until).toBe('2026-05-16T12:00:00.000Z');
      expect(new Date(result.since).getTime()).toBe(
        new Date('2026-05-16T12:00:00Z').getTime() - 180 * 86_400_000
      );
      vi.useRealTimers();
    });
  });

  describe('dashboardWindow', () => {
    it('returns a 180-day window ending at now', () => {
      vi.useFakeTimers().setSystemTime(new Date('2026-05-16T12:00:00Z'));
      const result = dashboardWindow();
      expect(result.until).toBe('2026-05-16T12:00:00.000Z');
      expect(new Date(result.since).getTime()).toBe(
        new Date('2026-05-16T12:00:00Z').getTime() - 180 * 86_400_000
      );
      vi.useRealTimers();
    });
  });

  describe('safeQuery', () => {
    it('returns parsed data when api.get resolves', async () => {
      const data = { hello: 'world' };
      const apiGetMock = api.get as unknown as vi.Mock;
      apiGetMock.mockResolvedValue({ data });

      const result = await safeQuery<typeof data>('/test', { q: '1' })();

      expect(result).toEqual(data);
      expect(api.get).toHaveBeenCalledWith('/test', { params: { q: '1' } });
    });

    it('returns null when api.get rejects', async () => {
      const apiGetMock = api.get as unknown as vi.Mock;
      apiGetMock.mockRejectedValue(new Error('fail'));
      const result = await safeQuery('/test')();
      expect(result).toBeNull();
    });
  });
});
