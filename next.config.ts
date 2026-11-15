import type { NextConfig } from 'next';
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8001';
const config: NextConfig = {
  async rewrites() {
    return [{ source: '/api/backend/:path*', destination: `${backend}/:path*` }];
  },
};
export default config;
