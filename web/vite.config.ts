import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins:[react()],
  define:{'process.env':{},global:'globalThis'},
  resolve:{alias:{events:'events/'}},
  server:{proxy:{'/api':'http://127.0.0.1:8000'}}
});
