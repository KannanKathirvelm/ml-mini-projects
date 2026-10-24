import type { CapacitorConfig } from '@capacitor/cli';

// The build script sets APP_ID / APP_NAME per flavor before `cap sync`.
// The real applicationId of each APK comes from Android productFlavors
// (android/app/build.gradle); this value only lands in assets/capacitor.config.json.
const config: CapacitorConfig = {
  appId: process.env.APP_ID || 'com.kannan.mlapps.upi',
  appName: process.env.APP_NAME || 'UPI Scam Shield',
  webDir: 'dist',
  server: { androidScheme: 'https' },
  android: {
    // The web view is served from https://localhost; the API may be plain http (10.0.2.2, LAN IP).
    allowMixedContent: true,
  },
};

export default config;
