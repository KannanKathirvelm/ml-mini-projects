// Plain list (no imports) so vite.config.ts and the build scripts can share it.
export const FLAVOR_IDS = ['creditcard', 'upi', 'stocks', 'finance', 'prices', 'faces', 'objects'] as const;
export type FlavorId = (typeof FLAVOR_IDS)[number];
