import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: '/vue/',
  root: '.',
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    open: '/index-vue.html',
    proxy: {
      '/api': {
        target: 'http://localhost:8788',
        changeOrigin: true,
      },
      '/shared': {
        target: 'http://localhost:8772',
        changeOrigin: true,
      },
      '/favicon.svg': {
        target: 'http://localhost:8772',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist-vue',
    assetsDir: 'assets',
  },
})
