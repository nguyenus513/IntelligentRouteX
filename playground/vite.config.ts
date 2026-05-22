import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/irx-api': {
        target: 'http://localhost:18116',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/irx-api/, '')
      },
      '/osrm-api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/osrm-api/, '')
      }
    }
  }
});
