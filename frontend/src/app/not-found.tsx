/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-lg font-semibold text-text-primary">Page not found</h1>
      <p className="max-w-md text-sm text-text-tertiary">
        The page you are looking for does not exist or was moved.
      </p>
      <Link href="/" className="text-sm text-text-tertiary underline hover:text-text-primary">
        Go home
      </Link>
    </main>
  );
}
