import { useCallback, useState } from 'react';

export type HeaderCheckboxState = 'checked' | 'indeterminate' | 'unchecked';

const DEFAULT_TOP_N = 50;

export type UseSelectionReturn<T> = {
  size: number;
  isSelected: (item: T) => boolean;
  toggle: (item: T) => void;
  clear: () => void;
  toggleTopN: (items: T[]) => void;
  headerState: (items: T[]) => HeaderCheckboxState;
  getSelected: (items: T[]) => T[];
};

export default function useSelection<T>(
  keyOf: (item: T) => string,
  topN: number = DEFAULT_TOP_N,
): UseSelectionReturn<T> {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());

  const toggle = useCallback(
    (item: T) => {
      const key = keyOf(item);
      setSelectedKeys((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
    },
    [keyOf],
  );

  const clear = useCallback(() => {
    setSelectedKeys((prev) => (prev.size === 0 ? prev : new Set()));
  }, []);

  const toggleTopN = useCallback(
    (items: T[]) => {
      setSelectedKeys((prev) => {
        if (prev.size > 0) return new Set();
        return new Set(items.slice(0, topN).map(keyOf));
      });
    },
    [keyOf, topN],
  );

  const isSelected = useCallback((item: T) => selectedKeys.has(keyOf(item)), [selectedKeys, keyOf]);

  const headerState = useCallback(
    (items: T[]): HeaderCheckboxState => {
      if (selectedKeys.size === 0) return 'unchecked';
      const visible = items.slice(0, topN);
      let matched = 0;
      for (const item of visible) {
        if (selectedKeys.has(keyOf(item))) matched++;
      }
      if (matched === visible.length && matched === selectedKeys.size) return 'checked';
      return 'indeterminate';
    },
    [selectedKeys, keyOf, topN],
  );

  const getSelected = useCallback(
    (items: T[]) => items.filter((item) => selectedKeys.has(keyOf(item))),
    [selectedKeys, keyOf],
  );

  return {
    size: selectedKeys.size,
    isSelected,
    toggle,
    clear,
    toggleTopN,
    headerState,
    getSelected,
  };
}
