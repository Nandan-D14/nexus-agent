"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch } from "@/lib/api-client";

export const dynamic = "force-dynamic";

/**
 * Handles the Google OAuth redirect after the user grants Drive access.
 * Reads query params from window.location.search (client-only popup).
 */
export default function GoogleDriveCallbackPage() {
  const { user, isLoading } = useAuth();
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("Connecting Google Drive...");

  useEffect(() => {
    if (isLoading) return;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const error = params.get("error");

    if (error) {
      setStatus("error");
      setMessage(`Google refused access: ${error}`);
      return;
    }

    if (!code || !state) {
      setStatus("error");
      setMessage("Missing code or state in redirect URL.");
      return;
    }

    if (!user) {
      setStatus("error");
      setMessage("Not authenticated. Please log in first.");
      return;
    }

    authenticatedFetch("/api/v1/auth/google-drive/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    })
      .then(() => {
        setStatus("success");
        setMessage("Google Drive connected!");
        if (window.opener) {
          window.opener.postMessage({ type: "google_drive_connected" }, window.location.origin);
          setTimeout(() => window.close(), 1200);
        }
      })
      .catch((err: unknown) => {
        setStatus("error");
        setMessage(`Connection failed: ${err instanceof Error ? err.message : "Unknown error"}`);
      });
  }, [isLoading, user]);

  const color =
    status === "success"
      ? "text-emerald-500"
      : status === "error"
        ? "text-red-400"
        : "text-cyan-400";

  const icon = status === "success" ? "✓" : status === "error" ? "✗" : "⋯";

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950">
      <div className="text-center space-y-4 px-8 max-w-sm">
        <p className="text-3xl font-mono">{icon}</p>
        <p className={`text-sm font-mono font-bold uppercase tracking-widest ${color}`}>
          {message}
        </p>
        {status === "error" && (
          <button
            onClick={() => window.close()}
            className="mt-4 px-4 py-2 text-xs text-zinc-400 border border-zinc-700 rounded-lg hover:border-zinc-500 transition-colors"
          >
            Close
          </button>
        )}
        {status === "pending" && (
          <div className="flex justify-center">
            <div className="h-4 w-4 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
