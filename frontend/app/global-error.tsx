"use client";

import { useEffect } from "react";

// global-error replaces the root layout entirely when it fires (an error
// thrown by the root layout itself, which app/error.tsx cannot catch --
// see Next.js's error.js file-convention docs) -- it must define its own
// <html>/<body>, not reuse app/layout.tsx's.
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <div
          style={{
            display: "flex",
            height: "100vh",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            textAlign: "center",
            padding: "1.5rem",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: "1.125rem", fontWeight: 500 }}>Something went wrong</h1>
          <p style={{ fontSize: "0.875rem", color: "#b91c1c" }}>
            An unexpected error occurred. Please try again.
          </p>
          <button
            onClick={() => unstable_retry()}
            style={{ fontSize: "0.8125rem", color: "#2563eb", textDecoration: "underline" }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
