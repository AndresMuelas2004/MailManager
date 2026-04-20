import { describe, expect, it } from 'vitest';

import { PROVIDER_META, PROVIDER_OPTIONS, getProviderMeta, isGenericLabel } from './providers';

describe('PROVIDER_META', () => {
  it('contains a gmail and an outlook entry', () => {
    expect(Object.keys(PROVIDER_META).sort()).toEqual(['gmail', 'outlook']);
  });

  it('every entry has a matching id and non-empty Tailwind classes', () => {
    for (const [key, meta] of Object.entries(PROVIDER_META)) {
      expect(meta.id).toBe(key);
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.friendlyName.length).toBeGreaterThan(0);
      expect(meta.dotClass.length).toBeGreaterThan(0);
    }
  });
});

describe('getProviderMeta', () => {
  it('returns the gmail meta for "gmail"', () => {
    expect(getProviderMeta('gmail').label).toBe('Gmail');
    expect(getProviderMeta('gmail').friendlyName).toBe('Google');
  });

  it('returns the outlook meta for "outlook"', () => {
    expect(getProviderMeta('outlook').label).toBe('Outlook');
    expect(getProviderMeta('outlook').friendlyName).toBe('Microsoft');
  });

  it('returns the fallback meta for unknown providers', () => {
    const meta = getProviderMeta('unknown-provider');
    expect(meta.label).toBe('Unknown');
    expect(meta.friendlyName).toBe('Unknown');
  });
});

describe('isGenericLabel', () => {
  it('returns true when the label equals the provider label', () => {
    expect(isGenericLabel('Gmail', 'gmail')).toBe(true);
    expect(isGenericLabel('Outlook', 'outlook')).toBe(true);
  });

  it('is case-insensitive against the provider key itself', () => {
    expect(isGenericLabel('GMAIL', 'gmail')).toBe(true);
    expect(isGenericLabel('outlook', 'outlook')).toBe(true);
  });

  it('returns false for a custom user-provided label', () => {
    expect(isGenericLabel('My work inbox', 'gmail')).toBe(false);
  });
});

describe('PROVIDER_OPTIONS', () => {
  it('mirrors PROVIDER_META as an array', () => {
    expect(PROVIDER_OPTIONS).toHaveLength(Object.keys(PROVIDER_META).length);
    expect(PROVIDER_OPTIONS.map((o) => o.id).sort()).toEqual(['gmail', 'outlook']);
  });
});
