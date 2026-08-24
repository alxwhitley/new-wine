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
  // Baseline browser security headers. Applied at the routing layer before
  // rendering, so statically prerendered pages stay static (verified: the
  // live homepage still serves x-vercel-cache: HIT after this landed).
  //
  // Strict-Transport-Security is deliberately absent: Vercel already sends
  // it on this domain (max-age=63072000, confirmed live). Setting it here
  // too would just be a second copy to keep in sync.
  //
  // Content-Security-Policy is deliberately absent as well, not overlooked.
  // A real CSP on App Router needs per-request middleware to issue a nonce,
  // which would opt every page out of static caching; the injection surface
  // it defends is also minimal here (no dangerouslySetInnerHTML anywhere,
  // and the markdown renderer escapes HTML by default). Recorded as
  // Scheduled B5 work in docs/roadmap.md instead of half-built here.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // No page in this app is ever framed (no iframe embeds anywhere),
          // so DENY is safe and stricter than SAMEORIGIN. Blocks an attacker
          // page from invisibly framing /admin and harvesting clicks from a
          // logged-in admin.
          { key: "X-Frame-Options", value: "DENY" },
          // Stop content-type guessing on served files.
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Send the full URL same-origin, origin-only cross-origin, and
          // nothing when downgrading to HTTP. Keeps question text in study
          // URLs from leaking to third parties via Referer.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // The app uses none of these APIs. Clipboard is intentionally NOT
          // restricted -- copy actions are a real feature here.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
