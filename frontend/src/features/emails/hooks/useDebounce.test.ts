import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useDebounce from './useDebounce';

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns the initial value synchronously on first render', () => {
    const { result } = renderHook(({ value }) => useDebounce(value, 300), {
      initialProps: { value: 'foo' },
    });
    expect(result.current).toBe('foo');
  });

  it('updates the debounced value after the delay elapses', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 300), {
      initialProps: { value: 'foo' },
    });

    rerender({ value: 'bar' });
    expect(result.current).toBe('foo'); // not yet — timer pending

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current).toBe('foo'); // still pending

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe('bar'); // commit
  });

  it('cancels the pending update when the value changes again before the delay', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 300), {
      initialProps: { value: 'foo' },
    });

    rerender({ value: 'bar' });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    rerender({ value: 'baz' });

    // After the original 300 ms total, the first scheduled update would have
    // committed 'bar' — but we re-rendered with 'baz', so the timer was reset.
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe('foo');

    // Only after a full 300 ms from the LAST change does 'baz' commit.
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe('baz');
  });

  it('only the most recent value commits when many changes happen within the window', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 300), {
      initialProps: { value: 'a' },
    });

    rerender({ value: 'ab' });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    rerender({ value: 'abc' });
    act(() => {
      vi.advanceTimersByTime(50);
    });
    rerender({ value: 'abcd' });

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current).toBe('abcd');
  });

  it('respects a custom delay value', () => {
    const { result, rerender } = renderHook(({ value, delay }) => useDebounce(value, delay), {
      initialProps: { value: 'foo', delay: 50 },
    });

    rerender({ value: 'bar', delay: 50 });
    act(() => {
      vi.advanceTimersByTime(49);
    });
    expect(result.current).toBe('foo');

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe('bar');
  });
});
