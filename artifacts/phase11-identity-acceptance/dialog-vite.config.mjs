import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
export default defineConfig({root:resolve(import.meta.dirname,'.dialog'),plugins:[react()],build:{outDir:'/tmp/apex-phase11-browser-dialog-dist',emptyOutDir:true}});
