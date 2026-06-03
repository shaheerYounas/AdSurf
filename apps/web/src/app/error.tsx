"use client";

import { useEffect } from "react";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Button } from "@/components/ui/button";
import { formatApiError } from "@/lib/api/client";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      console.error("Application error boundary caught an error", error);
    }
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center px-6 py-12">
      <ErrorNotice
        title="The app ran into a recoverable error"
        message={formatApiError(error, "The current page could not be displayed.")}
      />
      <div className="mt-4">
        <Button onClick={reset} type="button" variant="primary">
          Reload this view
        </Button>
      </div>
    </main>
  );
}
