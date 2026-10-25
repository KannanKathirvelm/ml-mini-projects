import { IonBadge, IonContent, IonHeader, IonPage, IonProgressBar, IonRefresher, IonRefresherContent, IonTitle, IonToolbar } from '@ionic/react';
import React, { useSyncExternalStore } from 'react';
import { serverWaking } from '../api/client';
import { useSettings } from '../settings';

/** onRefresh enables pull-to-refresh; the spinner stays until the returned promise settles. */
export const Page: React.FC<{ title: string; children: React.ReactNode; onRefresh?: () => unknown }> = ({ title, children, onRefresh }) => {
  const { settings } = useSettings();
  const waking = useSyncExternalStore(serverWaking.subscribe, serverWaking.get);
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonTitle>{title}</IonTitle>
          {settings.mock && <IonBadge slot="end" color="warning" className="mock-badge">MOCK</IonBadge>}
        </IonToolbar>
        {waking && !settings.mock && (
          <div className="waking-banner" role="status" aria-live="polite">
            <IonProgressBar type="indeterminate" color="warning" />
            <div className="waking-text">Server waking up… (free hosting, up to a minute)</div>
          </div>
        )}
      </IonHeader>
      <IonContent className="ion-padding">
        {onRefresh && (
          <IonRefresher slot="fixed" onIonRefresh={async (e) => { try { await onRefresh(); } finally { e.detail.complete(); } }}>
            <IonRefresherContent />
          </IonRefresher>
        )}
        <div className="page-inner">{children}</div>
      </IonContent>
    </IonPage>
  );
};
