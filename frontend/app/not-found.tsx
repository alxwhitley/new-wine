import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <h1 className="text-lg font-medium text-foreground">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        The page you&apos;re looking for doesn&apos;t exist.
      </p>
      <Link href="/" className="text-[13px] text-primary hover:underline transition-colors">
        Back to home
      </Link>
    </div>
  );
}
