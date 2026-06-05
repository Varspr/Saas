/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone — компактный прод-образ для Docker
  output: "standalone",
  // MVP: не валить прод-сборку из-за линтера (конфига ESLint нет)
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
