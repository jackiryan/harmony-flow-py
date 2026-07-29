import { defineConfig } from 'vite';

export default defineConfig({
    server: {
        proxy: {
            '/harmony-proxy': {
                target: 'https://harmony.uat.earthdata.nasa.gov',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/harmony-proxy/, ''),
                secure: true,
                configure: (proxy, _options) => {
                    proxy.on('error', (err, _req, _res) => {
                        console.log('Proxy error:', err);
                    });
                    proxy.on('proxyReq', (proxyReq, req, _res) => {
                        console.log('Proxying:', req.method, req.url);
                    });
                }
            }
        }
    }
});
