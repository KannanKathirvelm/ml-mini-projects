import { IonBadge, IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonCardTitle, IonChip, IonLabel, IonList } from '@ionic/react';
import { barChartOutline, shieldCheckmarkOutline } from 'ionicons/icons';
import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { UpiExample, UpiInput, UpiMeta, UpiResult } from '../api/types';
import { NumField, RangeField, SelectField, TextField, Toggle01 } from '../components/Form';
import { MetricsCard } from '../components/MetricsCard';
import { Page } from '../components/Page';
import { AsyncStatus } from '../components/Status';
import { BarRow, ProbabilityGauge, titleCase } from '../components/Widgets';
import { FLAVOR } from '../flavor';
import { useAsync, useLoad } from '../hooks';
import type { FeatureModule } from './types';

const BLANK: UpiInput = {
  payee_vpa: 'friend@okaxis', amount: 500, hour: 18, txn_type: 'P2P', mode: 'pay', is_new_payee: 0, payee_account_age_days: 700,
  payee_fraud_reports: 0, device_changed_48h: 0, sim_changed_48h: 0, failed_pin_attempts_24h: 0, txns_last_1h: 1, amount_to_avg_ratio: 1, remark: '',
};
const RISK_COLOR = { LOW: 'success', MEDIUM: 'warning', HIGH: 'danger' } as const;

const CheckPage: React.FC = () => {
  const ex = useLoad<UpiExample[]>(() => api.upi.examples());
  const [f, setF] = useState<UpiInput>(BLANK);
  const [picked, setPicked] = useState<string | null>(null);
  const res = useAsync<UpiResult>();
  const set = <K extends keyof UpiInput>(k: K) => (v: UpiInput[K]) => { setF((p) => ({ ...p, [k]: v })); setPicked(null); };
  useEffect(() => { if (ex.data?.length && picked === null && f === BLANK) { setF(ex.data[0].input); setPicked(ex.data[0].name); } }, [ex.data]); // eslint-disable-line

  const pick = (e: UpiExample) => { setF({ ...BLANK, ...e.input }); setPicked(e.name); res.reset(); };

  return (
    <Page title={FLAVOR.appName} onRefresh={ex.reload}>
      <IonCard>
        <IonCardHeader><IonCardSubtitle>Try an example</IonCardSubtitle></IonCardHeader>
        <IonCardContent>
          <AsyncStatus loading={ex.loading} slow={ex.slow} error={ex.error} onRetry={ex.reload} loadingLabel="Loading examples…" />
          <div className="chip-row">
            {ex.data?.map((e) => (
              <IonChip key={e.name} color={picked === e.name ? 'primary' : undefined} outline={picked !== e.name} onClick={() => pick(e)}>
                <IonLabel>{e.name}</IonLabel>
              </IonChip>
            ))}
          </div>
        </IonCardContent>
      </IonCard>

      <IonCard>
        <IonCardHeader><IonCardSubtitle>Payment details</IonCardSubtitle></IonCardHeader>
        <IonCardContent>
          <IonList className="form-grid" lines="full">
            <TextField label="Payee UPI ID (VPA)" value={f.payee_vpa} onChange={set('payee_vpa')} placeholder="name@bank" />
            <NumField label="Amount (₹)" value={f.amount} onChange={set('amount')} min={0} />
            <RangeField label="Hour of day" value={f.hour} onChange={set('hour')} min={0} max={23} step={1} format={(v) => `${v}:00`} />
            <SelectField label="Transaction type" value={f.txn_type} onChange={set('txn_type')}
              options={[{ value: 'P2P', label: 'P2P: person to person' }, { value: 'P2M', label: 'P2M: person to merchant' }]} />
            <SelectField label="Mode" value={f.mode} onChange={set('mode')}
              options={[{ value: 'pay', label: 'Pay' }, { value: 'collect_request', label: 'Collect request' }, { value: 'qr_scan', label: 'QR scan' }]} />
            <TextField label="Remark" value={f.remark} onChange={set('remark')} placeholder="optional note" />
            <Toggle01 label="New payee" value={f.is_new_payee} onChange={set('is_new_payee')} />
            <NumField label="Payee account age (days)" value={f.payee_account_age_days} onChange={set('payee_account_age_days')} min={0} step={1} />
            <NumField label="Fraud reports against payee" value={f.payee_fraud_reports} onChange={set('payee_fraud_reports')} min={0} step={1} />
            <Toggle01 label="Device changed (48 h)" value={f.device_changed_48h} onChange={set('device_changed_48h')} />
            <Toggle01 label="SIM changed (48 h)" value={f.sim_changed_48h} onChange={set('sim_changed_48h')} />
            <NumField label="Failed PIN attempts (24 h)" value={f.failed_pin_attempts_24h} onChange={set('failed_pin_attempts_24h')} min={0} step={1} />
            <NumField label="Transactions in last hour" value={f.txns_last_1h} onChange={set('txns_last_1h')} min={0} step={1} />
            <NumField label="Amount ÷ your average" value={f.amount_to_avg_ratio} onChange={set('amount_to_avg_ratio')} min={0} step={0.1} />
          </IonList>
          <IonButton expand="block" className="ion-margin-top" disabled={res.loading} onClick={() => res.run(() => api.upi.predict(f))}>
            Check payment
          </IonButton>
        </IonCardContent>
      </IonCard>

      <AsyncStatus loading={res.loading} slow={res.slow} error={res.error} loadingLabel="Analysing…" />
      {res.data && (
        <IonCard>
          <IonCardHeader>
            <IonCardSubtitle>Risk</IonCardSubtitle>
            <div><IonBadge className="risk-badge" color={RISK_COLOR[res.data.risk_level]}>{res.data.risk_level} RISK</IonBadge></div>
          </IonCardHeader>
          <IonCardContent>
            <ProbabilityGauge value={res.data.fraud_probability} threshold={res.data.threshold} />
            <p><strong>{res.data.flagged ? 'Do not approve this payment.' : 'No block recommended.'}</strong></p>
            {res.data.reasons.length > 0 && (
              <>
                <h3>Why</h3>
                <ul className="reason-list">{res.data.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </>
            )}
          </IonCardContent>
        </IonCard>
      )}
    </Page>
  );
};

const MetricsPage: React.FC = () => {
  const meta = useLoad<UpiMeta>(() => api.upi.meta());
  const byType = meta.data?.metrics.recall_by_fraud_type;
  return (
    <Page title="Model metrics" onRefresh={meta.reload}>
      <AsyncStatus loading={meta.loading} slow={meta.slow} error={meta.error} onRetry={meta.reload} />
      {meta.data && <MetricsCard metrics={meta.data.metrics} threshold={meta.data.threshold} />}
      {byType && (
        <IonCard>
          <IonCardHeader><IonCardTitle>Recall by scam type</IonCardTitle><IonCardSubtitle>Share of each scam type the model catches</IonCardSubtitle></IonCardHeader>
          <IonCardContent>
            {Object.entries(byType).map(([k, v]) => <BarRow key={k} label={titleCase(k)} value={v} color={v >= 0.95 ? 'success' : v >= 0.9 ? 'warning' : 'danger'} />)}
          </IonCardContent>
        </IonCard>
      )}
    </Page>
  );
};

const mod: FeatureModule = {
  tabs: [
    { path: '/check', label: 'Check', icon: shieldCheckmarkOutline, component: CheckPage },
    { path: '/metrics', label: 'Metrics', icon: barChartOutline, component: MetricsPage },
  ],
};
export default mod;
