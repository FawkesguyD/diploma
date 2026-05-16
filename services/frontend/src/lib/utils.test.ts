import { describe, it, expect } from 'vitest';
import { cn, formatNumber, formatPrice, formatDateTime } from './utils';

describe('cn', () => {
  it('merges classnames', () => {
    expect(cn('a', 'b')).toBe('a b');
  });
  it('dedupes tailwind conflicts', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
  });
  it('ignores falsy', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b');
  });
});

describe('formatNumber', () => {
  it('returns dash for null/undefined/NaN', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
    expect(formatNumber(Number.NaN)).toBe('—');
  });
  it('formats with ru-RU grouping', () => {
    const v = formatNumber(1234567);
    expect(v).toMatch(/1.234.567|1\u00a0234\u00a0567/);
  });
});

describe('formatPrice', () => {
  it('renders RUB currency', () => {
    const v = formatPrice(1500000);
    expect(v).toMatch(/₽/);
    expect(v).toMatch(/1/);
  });
  it('returns dash for empty', () => {
    expect(formatPrice(null)).toBe('—');
  });
});

describe('formatDateTime', () => {
  it('returns dash for empty', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('')).toBe('—');
  });
  it('formats ISO into ru locale string', () => {
    const v = formatDateTime('2026-05-15T12:30:00Z');
    expect(v).toMatch(/15\.05\.2026/);
  });
});
