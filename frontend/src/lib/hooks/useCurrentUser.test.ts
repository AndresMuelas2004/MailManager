import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../../test/msw/server';
import useCurrentUser from './useCurrentUser';

const API_BASE = 'http://localhost:8000';

describe('useCurrentUser', () => {
  it('fetchMe returns the user on success', async () => {
    const { result } = renderHook(() => useCurrentUser());

    let fetched;
    await act(async () => {
      fetched = await result.current.fetchMe();
    });

    expect(fetched).toEqual({
      user_id: 'u_test',
      email: 'tester@example.com',
      name: 'Tester',
      avatar_url: null,
    });
    expect(result.current.error).toBeNull();
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('fetchMe surfaces a UiError on a backend error response', async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json(
          { error: { code: 'unauthorized', message: 'Not logged in' } },
          { status: 401 },
        ),
      ),
    );

    const { result } = renderHook(() => useCurrentUser());

    let fetched;
    await act(async () => {
      fetched = await result.current.fetchMe();
    });

    expect(fetched).toBeNull();
    expect(result.current.error).toEqual({ message: 'Not logged in', code: 'unauthorized' });
  });

  it('deleteCurrentUser returns true on success', async () => {
    const { result } = renderHook(() => useCurrentUser());

    let ok;
    await act(async () => {
      ok = await result.current.deleteCurrentUser();
    });

    expect(ok).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it('deleteCurrentUser returns false and stores the error on failure', async () => {
    server.use(
      http.delete(`${API_BASE}/auth/me`, () =>
        HttpResponse.json(
          { error: { code: 'server_error', message: 'Could not delete user' } },
          { status: 500 },
        ),
      ),
    );

    const { result } = renderHook(() => useCurrentUser());

    let ok;
    await act(async () => {
      ok = await result.current.deleteCurrentUser();
    });

    expect(ok).toBe(false);
    expect(result.current.error?.code).toBe('server_error');
  });
});
