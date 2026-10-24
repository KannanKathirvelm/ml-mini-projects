import { IonBadge, IonContent, IonHeader, IonPage, IonRefresher, IonRefresherContent, IonTitle, IonToolbar } from '@ionic/react';
import React from 'react';
import { useSettings } from '../settings';

/** onRefresh enables pull-to-refresh; the spinner stays until the returned promise settles. */
export const Page: React.FC<{ title: string; children: React.ReactNode; onRefresh?: () => unknown }> = ({ title, children, onRefresh }) => {
  const { settings } = useSettings();
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar color="primary">
          <IonTitle>{title}</IonTitle>
          {settings.mock && <IonBadge slot="end" color="warning" className="mock-badge">MOCK</IonBadge>}
        </IonToolbar>
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
