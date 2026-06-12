import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/admin/contributors",
        destination: "/admin",
        permanent: true,
      },
      {
        source: "/rhemata-corpus-admin",
        destination: "/admin",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
