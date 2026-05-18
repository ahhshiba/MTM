/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // API Proxy: Forward /api/ocr/* to backend
  async rewrites() {
    return [
      {
        source: '/api/ocr/:path*',
        destination: 'http://backend:8001/local/ocr/:path*',
      },
    ]
  },
};

export default nextConfig;
