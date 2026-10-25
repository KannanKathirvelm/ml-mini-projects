import {
  IonButton, IonCard, IonCardContent, IonCardHeader, IonCardTitle, IonIcon, IonInput, IonItem, IonLabel, IonList, IonNote, IonSpinner, IonToggle,
} from '@ionic/react';
import { checkmarkCircle, closeCircle } from 'ionicons/icons';
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Health } from '../api/types';
import { Page } from '../components/Page';
import { FLAVOR } from '../flavor';
import { DEFAULT_SETTINGS, HOSTED_API_URL, useSettings } from '../settings';

const PRESETS: [string, string][] = [
  ['Build default', DEFAULT_SETTINGS.serverUrl],
  ...(DEFAULT_SETTINGS.serverUrl !== HOSTED_API_URL ? [['Hosted (Render)', HOSTED_API_URL] as [string, string]] : []),
  ['Emulator → host', 'http://10.0.2.2:7860'],
  ['Same machine (browser)', 'http://localhost:7860'],
];

const Settings: React.FC = () => {
  const { settings, update, reset } = useSettings();
  const [url, setUrl] = useState(settings.serverUrl);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string; ms?: number } | null>(null);
  useEffect(() => setUrl(settings.serverUrl), [settings.serverUrl]);

  const dirty = url.trim().replace(/\/+$/, '') !== settings.serverUrl;
  const save = () => update({ serverUrl: url });

  const test = async () => {
    if (dirty) await save();
    setTesting(true); setResult(null);
    const t0 = performance.now();
    try {
      const h: Health = await api.health();
      setResult({ ok: h.status === 'ok', text: `status "${h.status}", API v${h.version}, projects: ${h.projects.join(', ')}`, ms: Math.round(performance.now() - t0) });
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    } finally { setTesting(false); }
  };

  return (
    <Page title="Settings">
      <IonCard>
        <IonCardHeader><IonCardTitle>Server</IonCardTitle></IonCardHeader>
        <IonCardContent>
          <IonList lines="full">
            <IonItem>
              <IonInput label="Server URL" labelPlacement="stacked" type="url" inputmode="url" autocapitalize="off" autocorrect="off"
                value={url} placeholder="https://your-server.example.com" onIonInput={(e) => setUrl(String(e.detail.value ?? ''))} />
            </IonItem>
          </IonList>
          <div className="chip-row">
            {PRESETS.map(([label, u]) => (
              <IonButton key={label} size="small" fill="outline" onClick={() => setUrl(u)}>{label}</IonButton>
            ))}
          </div>
          <IonNote className="small">
            Real phone on Wi-Fi: use your computer's LAN IP, e.g. http://192.168.1.20:7860. The hosted server is on a free plan that sleeps after 15 minutes idle, so the first test can take up to a minute. Public tunnel URLs (e.g. trycloudflare.com) change whenever the tunnel restarts; paste the new one here.
          </IonNote>
          <div className="button-row">
            <IonButton disabled={!dirty} onClick={save}>Save</IonButton>
            <IonButton fill="outline" onClick={test} disabled={testing}>
              {testing ? <IonSpinner name="dots" /> : 'Test connection'}
            </IonButton>
          </div>
          {result && (
            <div className={`test-result ${result.ok ? 'ok' : 'bad'}`}>
              <IonIcon icon={result.ok ? checkmarkCircle : closeCircle} />
              <span>{result.ok ? `Connected${result.ms !== undefined ? ` in ${result.ms} ms` : ''}: ` : 'Failed: '}{result.text}</span>
            </div>
          )}
        </IonCardContent>
      </IonCard>

      <IonCard>
        <IonCardContent>
          <IonList lines="none">
            <IonItem>
              <IonToggle checked={settings.mock} onIonChange={(e) => update({ mock: e.detail.checked })}>
                <IonLabel>Mock mode<p>Use built-in sample responses; no server needed.</p></IonLabel>
              </IonToggle>
            </IonItem>
          </IonList>
        </IonCardContent>
      </IonCard>

      <IonCard>
        <IonCardContent>
          <IonList lines="full">
            <IonItem><IonLabel>App</IonLabel><IonNote slot="end">{FLAVOR.appName}</IonNote></IonItem>
            <IonItem><IonLabel>App ID</IonLabel><IonNote slot="end">{FLAVOR.appId}</IonNote></IonItem>
            <IonItem><IonLabel>Build default URL</IonLabel><IonNote slot="end">{DEFAULT_SETTINGS.serverUrl}</IonNote></IonItem>
          </IonList>
          <IonButton fill="clear" color="medium" size="small" onClick={reset}>Reset to defaults</IonButton>
        </IonCardContent>
      </IonCard>
    </Page>
  );
};
export default Settings;
