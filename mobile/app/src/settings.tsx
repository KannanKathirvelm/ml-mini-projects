import { Preferences } from '@capacitor/preferences';
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

export interface AppSettings { serverUrl: string; mock: boolean }

export const DEFAULT_SETTINGS: AppSettings = {
  serverUrl: (import.meta.env.VITE_API_URL || 'http://10.0.2.2:7860').replace(/\/+$/, ''),
  mock: String(import.meta.env.VITE_MOCK || 'false') === 'true',
};

const KEY = 'mlapps.settings.v1';

// Module-level copy so the API client can read settings without React.
let current: AppSettings = { ...DEFAULT_SETTINGS };
export const getSettings = () => current;

export async function loadSettings(): Promise<AppSettings> {
  try {
    const { value } = await Preferences.get({ key: KEY });
    if (value) current = { ...DEFAULT_SETTINGS, ...JSON.parse(value) };
  } catch {
    /* keep defaults */
  }
  return current;
}

async function persist(s: AppSettings) {
  current = s;
  await Preferences.set({ key: KEY, value: JSON.stringify(s) });
}

interface Ctx { settings: AppSettings; ready: boolean; update: (patch: Partial<AppSettings>) => Promise<void>; reset: () => Promise<void> }
const SettingsContext = createContext<Ctx | null>(null);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<AppSettings>(current);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadSettings().then((s) => { setSettings(s); setReady(true); });
  }, []);
  const update = useCallback(async (patch: Partial<AppSettings>) => {
    const next = { ...current, ...patch };
    if (patch.serverUrl !== undefined) next.serverUrl = patch.serverUrl.trim().replace(/\/+$/, '');
    await persist(next);
    setSettings(next);
  }, []);
  const reset = useCallback(async () => { await persist({ ...DEFAULT_SETTINGS }); setSettings({ ...DEFAULT_SETTINGS }); }, []);
  return <SettingsContext.Provider value={{ settings, ready, update, reset }}>{children}</SettingsContext.Provider>;
};

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings outside provider');
  return ctx;
}
