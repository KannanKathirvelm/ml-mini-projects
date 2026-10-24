import {
  IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonChip, IonItem, IonLabel, IonList, IonSelect, IonSelectOption,
} from '@ionic/react';
import { scanOutline } from 'ionicons/icons';
import React, { useState } from 'react';
import { api } from '../api/client';
import type { ObjectClasses, ObjectResult } from '../api/types';
import { RangeField } from '../components/Form';
import { ImagePicker, type PickedImage } from '../components/ImagePicker';
import { Page } from '../components/Page';
import { AsyncStatus, Empty, ErrorCard } from '../components/Status';
import { FLAVOR } from '../flavor';
import { useAsync, useLoad } from '../hooks';
import type { FeatureModule } from './types';

const DetectPage: React.FC = () => {
  const meta = useLoad<ObjectClasses>(() => api.objects.classes());
  const [img, setImg] = useState<PickedImage | null>(null);
  const [pickErr, setPickErr] = useState<Error | null>(null);
  const [conf, setConf] = useState(0.25);
  const [iou, setIou] = useState(0.7);
  const [classes, setClasses] = useState<string[]>([]);
  const [model, setModel] = useState('yolo11n.pt');
  const res = useAsync<ObjectResult>();
  const run = () => img && res.run(() => api.objects.detect(img.blob, { conf, iou, classes, model }));

  return (
    <Page title={FLAVOR.appName} onRefresh={meta.reload}>
      <IonCard>
        <IonCardContent>
          <ImagePicker onPick={(i) => { setImg(i); setPickErr(null); res.reset(); }} onError={setPickErr} />
          {pickErr && <ErrorCard error={pickErr} />}
          {img ? <img className="preview-img ion-margin-top" src={img.dataUrl} alt="Selected" /> : <Empty>Take a photo or pick one from the gallery.</Empty>}
        </IonCardContent>
      </IonCard>
      <IonCard>
        <IonCardContent>
          <AsyncStatus loading={meta.loading} slow={meta.slow} error={meta.error} onRetry={meta.reload} loadingLabel="Loading classes…" />
          <IonList lines="full">
            <IonItem>
              <IonSelect label="Model" labelPlacement="stacked" value={model} onIonChange={(e) => setModel(e.detail.value)} interface="action-sheet">
                {(meta.data?.models ?? ['yolo11n.pt']).map((m) => <IonSelectOption key={m} value={m}>{m}{m.includes('11n') ? ' (fast)' : m.includes('11s') ? ' (more accurate)' : ''}</IonSelectOption>)}
              </IonSelect>
            </IonItem>
            <IonItem>
              <IonSelect label="Only these classes" labelPlacement="stacked" multiple value={classes} placeholder="All 80 classes"
                onIonChange={(e) => setClasses(e.detail.value ?? [])} disabled={!meta.data}>
                {(meta.data?.classes ?? []).map((c) => <IonSelectOption key={c} value={c}>{c}</IonSelectOption>)}
              </IonSelect>
            </IonItem>
            <RangeField label="Confidence" value={conf} onChange={setConf} min={0.05} max={0.95} step={0.05} format={(v) => v.toFixed(2)} />
            <RangeField label="IoU (NMS)" value={iou} onChange={setIou} min={0.1} max={0.95} step={0.05} format={(v) => v.toFixed(2)} />
          </IonList>
          {classes.length > 0 && <IonButton size="small" fill="clear" onClick={() => setClasses([])}>Clear class filter</IonButton>}
          <IonButton expand="block" className="ion-margin-top" disabled={!img || res.loading} onClick={run}>Detect objects</IonButton>
        </IonCardContent>
      </IonCard>
      <AsyncStatus loading={res.loading} slow={res.slow} error={res.error} onRetry={run} loadingLabel="Uploading and detecting…"
        slowLabel="Server waking up or loading the YOLO model for the first time…" />
      {res.data && !res.loading && (
        <IonCard>
          <IonCardHeader>
            <IonCardSubtitle>{res.data.count} object{res.data.count === 1 ? '' : 's'} · {res.data.time_ms.toFixed(1)} ms · {model}</IonCardSubtitle>
            <div className="count-chips">
              {Object.entries(res.data.counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => <IonChip key={k} color="primary"><IonLabel>{k} × {v}</IonLabel></IonChip>)}
            </div>
          </IonCardHeader>
          <IonCardContent>
            <img className="result-img" src={`data:image/jpeg;base64,${res.data.image_base64}`} alt="Detections" />
            {res.data.count === 0 && <Empty>No objects above the confidence threshold. Try lowering it.</Empty>}
          </IonCardContent>
        </IonCard>
      )}
    </Page>
  );
};

const mod: FeatureModule = { tabs: [{ path: '/detect', label: 'Detect', icon: scanOutline, component: DetectPage }] };
export default mod;
