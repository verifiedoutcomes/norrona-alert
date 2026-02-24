"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

export default function VerifyPage() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"verifying" | "success" | "error">(
    "verifying",
  );
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      setErrorMessage("No token provided");
      return;
    }

    api.auth
      .verify(token)
      .then(() => {
        setStatus("success");
        // Redirect to dashboard after brief pause
        setTimeout(() => {
          window.location.href = "/";
        }, 1500);
      })
      .catch((err) => {
        setStatus("error");
        setErrorMessage(err.message || "Invalid or expired link");
      });
  }, [searchParams]);

  return (
    <div className="flex h-full items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        {status === "verifying" && (
          <>
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
            <p className="text-muted-foreground">Verifying your link...</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary-100">
              <svg
                className="h-6 w-6 text-primary-600"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4.5 12.75l6 6 9-13.5"
                />
              </svg>
            </div>
            <h1 className="text-lg font-semibold">You&apos;re signed in!</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Redirecting to dashboard...
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <svg
                className="h-6 w-6 text-red-600"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h1 className="text-lg font-semibold">Verification failed</h1>
            <p className="mt-1 text-sm text-muted-foreground">{errorMessage}</p>
            <a
              href="/"
              className="mt-4 inline-block rounded-lg bg-primary-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-600"
            >
              Back to login
            </a>
          </>
        )}
      </div>
    </div>
  );
}
