import flavors from './flavors.json';
import type { FlavorId } from './flavorIds';

export interface FlavorMeta {
  id: FlavorId;
  appId: string;
  appName: string;
  letter: string;
  color: string;
  description: string;
}

const id = (import.meta.env.VITE_APP_FLAVOR || 'upi') as FlavorId;
const meta = (flavors as Record<string, Omit<FlavorMeta, 'id' | 'appId'>>)[id];

export const FLAVOR: FlavorMeta = { id, appId: `com.kannan.mlapps.${id}`, ...meta };
