/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  webpack(config) {
    config.module.rules.push({
      test: /\.md$/,
      type: "asset/source",
    });
    return config;
  },
};

export default nextConfig;
