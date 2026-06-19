import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "jjerxncanaxlbdzcybab.supabase.co",
        pathname: "/storage/v1/object/public/**",
      },
    ],
  },
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
