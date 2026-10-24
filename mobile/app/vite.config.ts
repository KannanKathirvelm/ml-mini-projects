import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { FLAVOR_IDS } from './src/flavorIds';

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
  const flavor = env.VITE_APP_FLAVOR || 'upi';
  if (!FLAVOR_IDS.includes(flavor as never)) {
    throw new Error(`Unknown VITE_APP_FLAVOR "${flavor}". Use one of: ${FLAVOR_IDS.join(', ')}`);
  }
  return {
    plugins: [react()],
    base: './',
    define: {
      'import.meta.env.VITE_APP_FLAVOR': JSON.stringify(flavor),
    },
    build: {
      outDir: env.WEB_OUT_DIR || 'dist',
      emptyOutDir: true,
      chunkSizeWarningLimit: 1500,
    },
    server: { port: 5173, host: true },
  };
});
