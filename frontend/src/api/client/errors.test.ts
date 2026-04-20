import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import {
  ApiError,
  ValidationError,
  isApiError,
  isValidationError,
  toApiError,
  toNetworkError,
  toUiError,
} from './errors';

describe('toApiError', () => {
  it('parses a well-formed backend error envelope', () => {
    const err = toApiError(404, {
      error: { code: 'not_found', message: 'Mailbox missing' },
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('not_found');
    expect(err.message).toBe('Mailbox missing');
    expect(err.status).toBe(404);
  });

  it('falls back to http_error when the envelope is missing', () => {
    const err = toApiError(500, 'Internal Server Error');
    expect(err.code).toBe('http_error');
    expect(err.message).toBe('Internal Server Error');
    expect(err.status).toBe(500);
  });

  it('uses a generic message when the payload is empty', () => {
    const err = toApiError(500, null);
    expect(err.code).toBe('http_error');
    expect(err.message).toBe('Request failed');
  });
});

describe('toNetworkError', () => {
  it('wraps a network-level failure with the network_error code', () => {
    const err = toNetworkError('offline');
    expect(err.code).toBe('network_error');
    expect(err.status).toBeUndefined();
  });
});

describe('ValidationError', () => {
  it('extends ApiError with the schema_mismatch code and preserves issues', () => {
    const schema = z.object({ name: z.string() });
    const parsed = schema.safeParse({ name: 123 });
    if (parsed.success) throw new Error('expected schema to fail');

    const err = new ValidationError(parsed.error);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toBeInstanceOf(ValidationError);
    expect(err.code).toBe('schema_mismatch');
    expect(err.issues.length).toBeGreaterThan(0);
  });
});

describe('isApiError / isValidationError', () => {
  it('narrows ApiError instances', () => {
    expect(isApiError(new ApiError('x', 'y'))).toBe(true);
    expect(isApiError(new Error('x'))).toBe(false);
    expect(isApiError('x')).toBe(false);
  });

  it('narrows ValidationError instances without confusing plain ApiError', () => {
    const schema = z.object({ name: z.string() });
    const parsed = schema.safeParse({});
    if (parsed.success) throw new Error('unreachable');
    const validation = new ValidationError(parsed.error);
    expect(isValidationError(validation)).toBe(true);
    expect(isApiError(validation)).toBe(true);
    expect(isValidationError(new ApiError('x', 'y'))).toBe(false);
  });
});

describe('toUiError', () => {
  it('unwraps ApiError into { message, code }', () => {
    const ui = toUiError(new ApiError('denied', 'forbidden', 403));
    expect(ui).toEqual({ message: 'denied', code: 'forbidden' });
  });

  it('unwraps a plain Error into { message }', () => {
    const ui = toUiError(new Error('boom'));
    expect(ui).toEqual({ message: 'boom' });
  });

  it('unwraps a string', () => {
    expect(toUiError('literal')).toEqual({ message: 'literal' });
  });

  it('returns a generic message for unknown shapes', () => {
    expect(toUiError({ weird: true })).toEqual({ message: 'Unexpected error' });
    expect(toUiError(null)).toEqual({ message: 'Unexpected error' });
  });
});
