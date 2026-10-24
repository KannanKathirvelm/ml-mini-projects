import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { Capacitor } from '@capacitor/core';
import { IonButton, IonIcon } from '@ionic/react';
import { cameraOutline, imagesOutline } from 'ionicons/icons';
import React, { useRef } from 'react';

export interface PickedImage { blob: Blob; dataUrl: string }

async function dataUrlToBlob(url: string): Promise<Blob> {
  return (await fetch(url)).blob();
}

export const ImagePicker: React.FC<{ onPick: (img: PickedImage) => void; onError: (e: Error) => void }> = ({ onPick, onError }) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const native = Capacitor.isNativePlatform();

  const take = async (source: CameraSource) => {
    try {
      const photo = await Camera.getPhoto({
        source, resultType: CameraResultType.DataUrl, quality: 85, width: 1600, correctOrientation: true, allowEditing: false,
      });
      if (!photo.dataUrl) return;
      onPick({ blob: await dataUrlToBlob(photo.dataUrl), dataUrl: photo.dataUrl });
    } catch (e) {
      const msg = String((e as Error)?.message ?? e);
      if (/cancel/i.test(msg)) return; // user backed out
      onError(new Error(`Couldn't get a photo: ${msg}`));
    }
  };

  const onFile = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const f = ev.target.files?.[0];
    ev.target.value = '';
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { onError(new Error('Image is larger than 8 MB.')); return; }
    const r = new FileReader();
    r.onload = () => onPick({ blob: f, dataUrl: String(r.result) });
    r.readAsDataURL(f);
  };

  return (
    <div className="picker-row">
      <IonButton expand="block" onClick={() => (native ? take(CameraSource.Camera) : fileRef.current?.click())}>
        <IonIcon slot="start" icon={cameraOutline} /> Camera
      </IonButton>
      <IonButton expand="block" fill="outline" onClick={() => (native ? take(CameraSource.Photos) : fileRef.current?.click())}>
        <IonIcon slot="start" icon={imagesOutline} /> Gallery
      </IonButton>
      <input ref={fileRef} type="file" accept="image/jpeg,image/png" hidden onChange={onFile} />
    </div>
  );
};
