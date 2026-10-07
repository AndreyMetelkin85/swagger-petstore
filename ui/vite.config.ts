import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return { plugins: [react()], server: { proxy: { '/api': { target: env.LAPKI_API_TARGET || 'http://127.0.0.1:8080', changeOrigin: true } } } };
});
