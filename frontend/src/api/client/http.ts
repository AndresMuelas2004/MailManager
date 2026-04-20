import type { ZodType } from 'zod';
import { ApiError, ValidationError, toApiError, toNetworkError } from './errors';

const DEFAULT_BASE_URL = 'http://localhost:8000';
const DEFAULT_HEADERS: HeadersInit = {
  Accept: 'application/json',
};

type RequestOptions<T> = {
  method?: string;
  headers?: HeadersInit;
  body?: unknown;
  signal?: AbortSignal;
  schema?: ZodType<T>;
};

function getBaseUrl(): string {
  const envBase =
    typeof import.meta !== 'undefined'
      ? (import.meta.env?.VITE_API_BASE_URL as string | undefined)
      : undefined;
  return envBase && envBase.length > 0 ? envBase : DEFAULT_BASE_URL;
}

function buildUrl(path: string): string {
  const base = getBaseUrl().replace(/\/+$/, '');
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalized}`;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  const text = await response.text();
  return text.length > 0 ? text : undefined;
}

export async function request<T>(path: string, options: RequestOptions<T> = {}): Promise<T> {
  const url = buildUrl(path);
  const headers: HeadersInit = {
    ...DEFAULT_HEADERS,
    ...options.headers,
  };

  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers,
    signal: options.signal,
    credentials: 'include',
  };

  if (options.body !== undefined) {
    (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  let data: unknown;
  try {
    response = await fetch(url, init);
    data = await parseBody(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw toNetworkError('Network error while contacting the API.');
  }

  if (!response.ok) {
    throw toApiError(response.status, data);
  }

  if (options.schema) {
    const parsed = options.schema.safeParse(data);
    if (!parsed.success) {
      throw new ValidationError(parsed.error);
    }
    return parsed.data;
  }

  return data as T;
}
