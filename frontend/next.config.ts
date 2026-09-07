import type { NextConfig } from 'next';
const config: NextConfig = { poweredByHeader: false, devIndicators: false, distDir: process.env.GEO_NEXT_DIST_DIR || ".next" };
export default config;
