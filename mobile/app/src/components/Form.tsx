import { IonInput, IonItem, IonLabel, IonRange, IonSelect, IonSelectOption, IonToggle } from '@ionic/react';
import React from 'react';

export const NumField: React.FC<{ label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; helper?: string }> =
  ({ label, value, onChange, min, max, step, helper }) => (
    <IonItem>
      <IonInput label={label} labelPlacement="stacked" type="number" inputmode="decimal" value={value} min={min} max={max} step={step ? String(step) : undefined}
        helperText={helper} onIonInput={(e) => { const v = parseFloat(String(e.detail.value)); if (!Number.isNaN(v)) onChange(v); }} />
    </IonItem>
  );

export const TextField: React.FC<{ label: string; value: string; onChange: (v: string) => void; placeholder?: string }> = ({ label, value, onChange, placeholder }) => (
  <IonItem>
    <IonInput label={label} labelPlacement="stacked" value={value} placeholder={placeholder} autocapitalize="off" onIonInput={(e) => onChange(String(e.detail.value ?? ''))} />
  </IonItem>
);

export const Toggle01: React.FC<{ label: string; value: 0 | 1; onChange: (v: 0 | 1) => void; hint?: string }> = ({ label, value, onChange, hint }) => (
  <IonItem>
    <IonToggle checked={value === 1} onIonChange={(e) => onChange(e.detail.checked ? 1 : 0)}>
      <IonLabel>{label}{hint && <p>{hint}</p>}</IonLabel>
    </IonToggle>
  </IonItem>
);

export function SelectField<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <IonItem>
      <IonSelect label={label} labelPlacement="stacked" interface="action-sheet" value={value} onIonChange={(e) => onChange(e.detail.value as T)}>
        {options.map((o) => <IonSelectOption key={o.value} value={o.value}>{o.label}</IonSelectOption>)}
      </IonSelect>
    </IonItem>
  );
}

export const RangeField: React.FC<{ label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; format?: (v: number) => string }> =
  ({ label, value, onChange, min, max, step, format = (v) => String(v) }) => (
    <IonItem>
      <IonRange labelPlacement="stacked" label={`${label}: ${format(value)}`} min={min} max={max} step={step} value={value} pin pinFormatter={format}
        onIonInput={(e) => onChange(e.detail.value as number)} />
    </IonItem>
  );
