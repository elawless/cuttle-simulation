import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			// WebSocket endpoint - must come before /api to match first
			'/api/ws': {
				target: 'ws://localhost:8000',
				ws: true,
				changeOrigin: true
			},
			// REST API endpoints
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true
			}
		}
	}
});
