import { IonApp, IonIcon, IonLabel, IonRouterOutlet, IonSpinner, IonTabBar, IonTabButton, IonTabs, setupIonicReact } from '@ionic/react';
import { IonReactRouter } from '@ionic/react-router';
import { settingsOutline } from 'ionicons/icons';
import React, { useEffect, useState } from 'react';
import { Redirect, Route } from 'react-router-dom';
import type { FeatureModule } from './features/types';
import Settings from './pages/Settings';
import { wakeServer } from './api/client';
import { SettingsProvider, useSettings } from './settings';

setupIonicReact({ mode: 'md' });

// VITE_APP_FLAVOR is a build-time constant, so Rollup drops every branch except the built flavor:
// each APK only contains its own feature code.
const F = import.meta.env.VITE_APP_FLAVOR;
const loadFeature = (): Promise<{ default: FeatureModule }> =>
  F === 'creditcard' ? import('./features/creditcard')
    : F === 'upi' ? import('./features/upi')
      : F === 'stocks' ? import('./features/stocks')
        : F === 'finance' ? import('./features/finance')
          : F === 'prices' ? import('./features/prices')
            : F === 'faces' ? import('./features/faces')
              : import('./features/objects');

const Shell: React.FC = () => {
  const { ready } = useSettings();
  const [mod, setMod] = useState<FeatureModule | null>(null);
  useEffect(() => { loadFeature().then((m) => setMod(m.default)); }, []);
  // Start waking a sleeping (free-tier) server as soon as the saved URL is known.
  useEffect(() => { if (ready) wakeServer(); }, [ready]);
  if (!ready || !mod) return <div className="boot"><IonSpinner name="crescent" /></div>;
  return (
    <IonReactRouter>
      <IonTabs>
        <IonRouterOutlet>
          {mod.tabs.map((t) => <Route key={t.path} exact path={t.path} component={t.component} />)}
          <Route exact path="/settings" component={Settings} />
          <Route exact path="/"><Redirect to={mod.tabs[0].path} /></Route>
        </IonRouterOutlet>
        <IonTabBar slot="bottom">
          {mod.tabs.map((t) => (
            <IonTabButton key={t.path} tab={t.path} href={t.path}>
              <IonIcon aria-hidden icon={t.icon} /><IonLabel>{t.label}</IonLabel>
            </IonTabButton>
          ))}
          <IonTabButton tab="settings" href="/settings">
            <IonIcon aria-hidden icon={settingsOutline} /><IonLabel>Settings</IonLabel>
          </IonTabButton>
        </IonTabBar>
      </IonTabs>
    </IonReactRouter>
  );
};

const App: React.FC = () => (
  <IonApp>
    <SettingsProvider><Shell /></SettingsProvider>
  </IonApp>
);
export default App;
