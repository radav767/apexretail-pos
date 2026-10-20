import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Shared POS components must use the Backoffice renderer's React instance.
  resolve: { dedupe: ['react', 'react-dom'] },
})
