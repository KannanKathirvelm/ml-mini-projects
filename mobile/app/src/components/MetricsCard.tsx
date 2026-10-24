import { IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle } from '@ionic/react';
import React from 'react';
import type { ModelMetrics } from '../api/types';
import { BarRow, KeyValueList, pct, titleCase } from './Widgets';

export const MetricsCard: React.FC<{ metrics: ModelMetrics; threshold: number }> = ({ metrics, threshold }) => (
  <IonCard>
    <IonCardHeader>
      <IonCardSubtitle>Model performance (held-out test set)</IonCardSubtitle>
      <IonCardTitle>{metrics.best_model ? titleCase(String(metrics.best_model)) : 'Model'}</IonCardTitle>
    </IonCardHeader>
    <IonCardContent>
      <BarRow label="Fraud precision" value={metrics.fraud_precision} />
      <BarRow label="Fraud recall" value={metrics.fraud_recall} />
      <BarRow label="Average precision (PR-AUC)" value={metrics.average_precision} />
      <BarRow label="ROC-AUC" value={metrics.roc_auc} />
      <KeyValueList rows={[['Decision threshold', pct(threshold, 1)]]} />
    </IonCardContent>
  </IonCard>
);
