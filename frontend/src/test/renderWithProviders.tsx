import { type ReactElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';

import { AuthContext, type AuthState } from '../app/providers/AuthContext';
import type { UserOut } from '../api/types/dto';

type ProvidersOptions = {
  initialEntries?: string[];
  user?: UserOut | null;
  queryClient?: QueryClient;
};

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function buildAuthValue(user: UserOut | null): AuthState {
  return {
    user,
    loading: false,
    error: null,
    login: () => Promise.resolve(),
    logout: () => Promise.resolve(),
  };
}

// eslint-disable-next-line react-refresh/only-export-components
function TestProviders({
  children,
  initialEntries,
  user,
  queryClient,
}: ProvidersOptions & { children: ReactNode }) {
  const client = queryClient ?? createTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <AuthContext.Provider value={buildAuthValue(user ?? null)}>
        <MemoryRouter initialEntries={initialEntries ?? ['/']}>{children}</MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

/**
 * Render a component inside the same provider stack the app uses in
 * production (TanStack Query, auth context, React Router). Individual
 * tests can override the initial route, the authenticated user, or the
 * query client to exercise specific scenarios.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: ProvidersOptions & Omit<RenderOptions, 'wrapper'> = {},
): RenderResult {
  const { initialEntries, user, queryClient, ...renderOptions } = options;
  return render(ui, {
    wrapper: ({ children }) => (
      <TestProviders initialEntries={initialEntries} user={user} queryClient={queryClient}>
        {children}
      </TestProviders>
    ),
    ...renderOptions,
  });
}
