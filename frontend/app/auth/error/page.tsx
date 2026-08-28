import Link from "next/link";

export default function AuthErrorPage() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-background">
      <div className="w-full max-w-sm mx-4 rounded-lg border border-border bg-card shadow-lg p-6 text-center">
        <h2 className="font-sans text-xl font-semibold text-foreground mb-2">
          Link expired
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Invalid or expired link. Please request a new password reset.
        </p>
        <Link
          href="/"
          className="text-sm text-primary hover:underline"
        >
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
