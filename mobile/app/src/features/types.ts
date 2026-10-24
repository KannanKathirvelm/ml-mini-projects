import type React from 'react';

export interface TabDef { path: string; label: string; icon: string; component: React.ComponentType }
export interface FeatureModule { tabs: TabDef[] }
