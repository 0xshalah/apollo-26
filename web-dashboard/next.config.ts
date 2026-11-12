import path from 'node:path';
import type { NextConfig } from 'next';

/** Normalizes NEXT_PUBLIC_BASE_PATH: "" for daemon hosting, "/apollo-26" for GitHub Pages. */
function normalizeBasePath(raw: string | undefined): string {
  const trimmed = (raw ?? '').trim().replace(/\/+$/, '');
  if (trimmed === '' || trimmed === '/') return '';
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}

const basePath = normalizeBasePath(process.env.NEXT_PUBLIC_BASE_PATH);
// Contracts live one directory above the app and are imported at build time.
const repoRoot = path.resolve(process.cwd(), '..');

const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  basePath,
  assetPrefix: basePath || undefined,
  images: { unoptimized: true },
  poweredByHeader: false,
  reactStrictMode: true,
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
  outputFileTracingRoot: repoRoot,
  turbopack: { root: repoRoot },
};

export default nextConfig;
