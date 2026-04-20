import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import useSelection from './useSelection';

type Item = { id: string; name: string };
const keyOf = (i: Item) => i.id;

const a: Item = { id: 'a', name: 'A' };
const b: Item = { id: 'b', name: 'B' };
const c: Item = { id: 'c', name: 'C' };

describe('useSelection', () => {
  it('starts empty', () => {
    const { result } = renderHook(() => useSelection(keyOf));
    expect(result.current.size).toBe(0);
    expect(result.current.isSelected(a)).toBe(false);
  });

  it('toggles a single item on and off', () => {
    const { result } = renderHook(() => useSelection(keyOf));
    act(() => result.current.toggle(a));
    expect(result.current.size).toBe(1);
    expect(result.current.isSelected(a)).toBe(true);

    act(() => result.current.toggle(a));
    expect(result.current.size).toBe(0);
    expect(result.current.isSelected(a)).toBe(false);
  });

  it('clear empties the selection', () => {
    const { result } = renderHook(() => useSelection(keyOf));
    act(() => {
      result.current.toggle(a);
      result.current.toggle(b);
    });
    expect(result.current.size).toBe(2);

    act(() => result.current.clear());
    expect(result.current.size).toBe(0);
  });

  it('toggleTopN selects up to N items when nothing is selected, and clears otherwise', () => {
    const { result } = renderHook(() => useSelection(keyOf, 2));
    act(() => result.current.toggleTopN([a, b, c]));
    expect(result.current.size).toBe(2);
    expect(result.current.isSelected(a)).toBe(true);
    expect(result.current.isSelected(b)).toBe(true);
    expect(result.current.isSelected(c)).toBe(false);

    act(() => result.current.toggleTopN([a, b, c]));
    expect(result.current.size).toBe(0);
  });

  it('headerState reflects visibility', () => {
    const { result } = renderHook(() => useSelection(keyOf, 2));
    expect(result.current.headerState([a, b, c])).toBe('unchecked');

    act(() => result.current.toggle(a));
    expect(result.current.headerState([a, b, c])).toBe('indeterminate');

    act(() => result.current.toggle(b));
    // both visible-top-N items selected and nothing beyond
    expect(result.current.headerState([a, b, c])).toBe('checked');
  });

  it('getSelected returns only the currently-selected items from a given list', () => {
    const { result } = renderHook(() => useSelection(keyOf));
    act(() => {
      result.current.toggle(a);
      result.current.toggle(c);
    });
    const selected = result.current.getSelected([a, b, c]);
    expect(selected).toEqual([a, c]);
  });
});
