import { ApiError, toApiError, toNetworkError } from './errors';

const DEFAULT_BASE_URL = 'http://localhost:8000';
const DEFAULT_HEADERS: HeadersInit = {
  Accept: 'application/json',
};

type RequestOptions = {
  method?: string;
  headers?: HeadersInit;
  body?: unknown;
  signal?: AbortSignal;
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

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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

  try {
    const response = await fetch(url, init);
    const data = await parseBody(response);

    if (!response.ok) {
      throw toApiError(response.status, data);
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw toNetworkError('Network error while contacting the API.');
  }
}
