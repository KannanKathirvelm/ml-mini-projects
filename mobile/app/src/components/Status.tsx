import { IonButton, IonCard, IonCardContent, IonIcon, IonNote, IonSpinner, IonText } from '@ionic/react';
import { alertCircleOutline, cloudOfflineOutline, refreshOutline } from 'ionicons/icons';
import React from 'react';
import { ApiError } from '../api/client';

export const Loading: React.FC<{ slow?: boolean; label?: string; slowLabel?: string }> = ({ slow, label = 'Loading…', slowLabel }) => (
  <div className="status-box" role="status" aria-live="polite">
    <IonSpinner name="crescent" />
    <div>
      <div>{label}</div>
      {slow && (
        <IonNote className="small">
          {slowLabel ?? 'Server waking up… the first request after a restart can take up to a minute.'}
        </IonNote>
      )}
    </div>
  </div>
);

export const ErrorCard: React.FC<{ error: Error; onRetry?: () => void }> = ({ error, onRetry }) => {
  const net = error instanceof ApiError && (error.kind === 'network' || error.kind === 'timeout');
  const status = error instanceof ApiError && error.status ? ` (HTTP ${error.status})` : '';
  return (
    <IonCard color="danger" className="error-card">
      <IonCardContent>
        <div className="row-center">
          <IonIcon icon={net ? cloudOfflineOutline : alertCircleOutline} size="large" />
          <IonText>
            <strong>{net ? 'Server unreachable' : 'Request failed'}{status}</strong>
            <div>{error.message}</div>
          </IonText>
        </div>
        {onRetry && (
          <IonButton fill="outline" color="light" size="small" onClick={onRetry}>
            <IonIcon slot="start" icon={refreshOutline} /> Retry
          </IonButton>
        )}
        {net && <IonButton fill="clear" color="light" size="small" routerLink="/settings">Open Settings</IonButton>}
      </IonCardContent>
    </IonCard>
  );
};

export const Empty: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="empty-box"><IonNote>{children}</IonNote></div>
);

interface AsyncViewProps { loading: boolean; slow?: boolean; error: Error | null; onRetry?: () => void; loadingLabel?: string; slowLabel?: string }
/** Renders loading / error; returns null when neither applies. */
export const AsyncStatus: React.FC<AsyncViewProps> = ({ loading, slow, error, onRetry, loadingLabel, slowLabel }) => {
  if (loading) return <Loading slow={slow} label={loadingLabel} slowLabel={slowLabel} />;
  if (error) return <ErrorCard error={error} onRetry={onRetry} />;
  return null;
};
