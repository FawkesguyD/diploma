import axios, { AxiosError, type AxiosInstance } from 'axios';

const TOKEN_KEY = 'ais_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      setStoredToken(null);
      onUnauthorized?.();
    }
    return Promise.reject(error);
  }
);

export function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data as { detail?: string; title?: string; message?: string } | undefined;
    return data?.detail ?? data?.title ?? data?.message ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return 'Неизвестная ошибка';
}
