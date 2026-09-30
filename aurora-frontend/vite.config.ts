import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // Expose only VITE_* variables (Vite default). Listed explicitly so the
  // contract is visible and cannot be widened by accident.
  envPrefix: ['VITE_'],
  server: {
    port: 5173,
    strictPort: false,
  },
});
