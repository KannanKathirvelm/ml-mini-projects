import { IonButton, IonCard, IonCardContent, IonCardHeader, IonCardSubtitle, IonChip, IonList, IonSegment, IonSegmentButton, IonLabel, IonItem, IonToggle } from '@ionic/react';
import { happyOutline } from 'ionicons/icons';
import React, { useState } from 'react';
import { api } from '../api/client';
import type { FaceDetector, FaceResult } from '../api/types';
import { RangeField } from '../components/Form';
import { ImagePicker, type PickedImage } from '../components/ImagePicker';
import { Page } from '../components/Page';
import { AsyncStatus, Empty, ErrorCard } from '../components/Status';
import { FLAVOR } from '../flavor';
import { useAsync } from '../hooks';
import type { FeatureModule } from './types';

const NAMES = { yunet: 'YuNet (DNN)', haar: 'Haar cascade' } as const;

const DetectPage: React.FC = () => {
  const [img, setImg] = useState<PickedImage | null>(null);
  const [pickErr, setPickErr] = useState<Error | null>(null);
  const [detector, setDetector] = useState<FaceDetector>('yunet');
  const [blur, setBlur] = useState(false);
  const [threshold, setThreshold] = useState(0.6);
  const res = useAsync<FaceResult>();

  const run = (i = img) => i && res.run(() => api.faces.detect(i.blob, { detector, blur, threshold }));

  return (
    <Page title={FLAVOR.appName} onRefresh={() => (img ? run() : undefined)}>
      <IonCard>
        <IonCardContent>
          <ImagePicker onPick={(i) => { setImg(i); setPickErr(null); res.reset(); }} onError={setPickErr} />
          {pickErr && <ErrorCard error={pickErr} />}
          {img ? <img className="preview-img ion-margin-top" src={img.dataUrl} alt="Selected" /> : <Empty>Take a photo or pick one from the gallery.</Empty>}
        </IonCardContent>
      </IonCard>
      <IonCard>
        <IonCardContent>
          <IonSegment value={detector} onIonChange={(e) => setDetector(e.detail.value as FaceDetector)}>
            <IonSegmentButton value="yunet"><IonLabel>YuNet</IonLabel></IonSegmentButton>
            <IonSegmentButton value="haar"><IonLabel>Haar</IonLabel></IonSegmentButton>
            <IonSegmentButton value="both"><IonLabel>Both</IonLabel></IonSegmentButton>
          </IonSegment>
          <IonList lines="full">
            <IonItem><IonToggle checked={blur} onIonChange={(e) => setBlur(e.detail.checked)}>Blur faces (privacy)</IonToggle></IonItem>
            <RangeField label="YuNet confidence" value={threshold} onChange={setThreshold} min={0.1} max={0.95} step={0.05} format={(v) => v.toFixed(2)} />
          </IonList>
          <IonButton expand="block" className="ion-margin-top" disabled={!img || res.loading} onClick={() => run()}>Detect faces</IonButton>
        </IonCardContent>
      </IonCard>
      <AsyncStatus loading={res.loading} slow={res.slow} error={res.error} onRetry={() => run()} loadingLabel="Uploading and detecting…" />
      {res.data?.results.map((r) => (
        <IonCard key={r.detector}>
          <IonCardHeader>
            <IonCardSubtitle>{NAMES[r.detector] ?? r.detector}</IonCardSubtitle>
            <div className="count-chips">
              <IonChip color="primary">{r.count} face{r.count === 1 ? '' : 's'}</IonChip>
              <IonChip outline>{r.time_ms.toFixed(1)} ms</IonChip>
            </div>
          </IonCardHeader>
          <IonCardContent>
            <img className="result-img" src={`data:image/jpeg;base64,${r.image_base64}`} alt={`${r.detector} result`} />
          </IonCardContent>
        </IonCard>
      ))}
    </Page>
  );
};

const mod: FeatureModule = { tabs: [{ path: '/detect', label: 'Detect', icon: happyOutline, component: DetectPage }] };
export default mod;
