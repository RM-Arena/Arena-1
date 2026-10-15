import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({root:path.resolve('frontend'),plugins:[react()],publicDir:'public',build:{outDir:'dist',emptyOutDir:true},server:{host:'127.0.0.1',port:5173,proxy:{'/api':{target:'http://127.0.0.1:8765',ws:true}}}});
