import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // the FastAPI backend (uv run uvicorn tactics.api:app) serves /api on port 8000
    proxy: { '/api': 'http://localhost:8000' },
  },
});
