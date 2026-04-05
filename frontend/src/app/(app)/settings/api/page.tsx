"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Loader2,
  Save,
  Server,
} from "lucide-react";

import { useToast } from "@/components/toast-provider";
import {
  type GeminiProvider,
  type UserSettingsResponse,
  fetchUserSettings,
  updateUserSettings,
} from "@/lib/user-settings";

function missingLabel(key: string, provider: GeminiProvider, vertexConfigured: boolean) {
  if (key === "e2b") {
    return "E2B API key or access code";
  }
  if (key === "accessCode") {
    return "Access code for shared Vertex AI";
  }
  if (key === "vertex") {
    return "Vertex AI server configuration";
  }
  if (provider === "vertex" && !vertexConfigured) {
    return "Vertex AI server configuration";
  }
  return "Gemini API key";
}

export default function ApiSettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();

  const [settings, setSettings] = useState<UserSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [e2bApiKey, setE2bApiKey] = useState("");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [geminiProvider, setGeminiProvider] = useState<GeminiProvider>("apiKey");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetchUserSettings();
        if (cancelled) {
          return;
        }
        setSettings(response);
        setGeminiProvider(response.byok.geminiProvider);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load API settings.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const blockingCallout = useMemo(() => {
    if (!settings) {
      return false;
    }
    return searchParams.get("setup") === "1" || (settings.requireByok && settings.byok.missing.length > 0);
  }, [searchParams, settings]);

  const missingItems = useMemo(() => {
    if (!settings) {
      return [];
    }
    return settings.byok.missing.map((key) =>
      missingLabel(key, geminiProvider, settings.byok.vertexConfigured),
    );
  }, [geminiProvider, settings]);

  const sharedE2bReady = Boolean(
    settings?.byok.sharedAccessEnabled && settings.byok.serverE2bConfigured,
  );
  const sharedVertexReady = Boolean(
    settings?.byok.sharedAccessEnabled && settings.byok.vertexConfigured,
  );
  const e2bReady = Boolean(settings?.byok.e2bKeySet || sharedE2bReady);
  const geminiReady = Boolean(
    settings &&
      (geminiProvider === "vertex" ? sharedVertexReady : settings.byok.geminiKeySet),
  );

  const handleSave = async () => {
    if (!settings) {
      return;
    }

    const hasPendingAccessCode = accessCode.trim().length > 0;
    const nextHasE2b =
      settings.byok.e2bKeySet ||
      e2bApiKey.trim().length > 0 ||
      sharedE2bReady ||
      hasPendingAccessCode;
    const nextHasGemini =
      geminiProvider === "vertex"
        ? sharedVertexReady || hasPendingAccessCode
        : settings.byok.geminiKeySet || geminiApiKey.trim().length > 0;

    if (settings.requireByok && !nextHasE2b) {
      setError(
        settings.byok.sharedAccessCodeConfigured && settings.byok.serverE2bConfigured
          ? "An E2B API key or a valid access code is required before you can start a session."
          : "An E2B API key is required before you can start a session.",
      );
      return;
    }

    if (geminiProvider === "vertex" && !settings.byok.vertexConfigured) {
      setError("Vertex AI is not configured on the server. Switch to Gemini API Key instead.");
      return;
    }

    if (geminiProvider === "vertex" && !sharedVertexReady && !hasPendingAccessCode) {
      setError(
        settings.byok.sharedAccessCodeConfigured
          ? "Enter the access code to unlock shared Vertex AI credits before saving Vertex AI."
          : "Shared Vertex AI credits are not available for this account.",
      );
      return;
    }

    if (settings.requireByok && !nextHasGemini) {
      setError(
        geminiProvider === "vertex" && settings.byok.sharedAccessCodeConfigured
          ? "Enter a valid access code to unlock shared Vertex AI credits, or switch to Gemini API Key."
          : geminiProvider === "vertex" && !settings.byok.vertexConfigured
            ? "Vertex AI is not configured on the server. Use a Gemini API key instead."
          : "Choose a Gemini provider and supply the required key before saving.",
      );
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const payload: {
        byok: {
          geminiProvider: GeminiProvider;
          e2bApiKey?: string;
          geminiApiKey?: string;
          accessCode?: string;
        };
      } = {
        byok: {
          geminiProvider,
        },
      };

      if (e2bApiKey.trim()) {
        payload.byok.e2bApiKey = e2bApiKey.trim();
      }

      if (geminiProvider === "apiKey" && geminiApiKey.trim()) {
        payload.byok.geminiApiKey = geminiApiKey.trim();
      }

      if (accessCode.trim()) {
        payload.byok.accessCode = accessCode.trim();
      }

      const updated = await updateUserSettings(payload);
      setSettings(updated);
      setAccessCode("");
      setE2bApiKey("");
      setGeminiApiKey("");
      setGeminiProvider(updated.byok.geminiProvider);
      toast("API & Keys saved.", "success");

      if (searchParams.get("setup") === "1" && updated.byok.missing.length === 0) {
        router.replace("/settings/api");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save API settings.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-3xl border border-error/20 bg-error/5 p-6 text-sm text-error">
        {error || "Failed to load API settings."}
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-3xl text-foreground">
      <div className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-card-border bg-muted/50 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          <KeyRound className="h-3.5 w-3.5" />
          API & Keys
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight mb-2">
            Bring Your Own Keys
          </h2>
          <p className="text-sm text-muted-foreground font-medium">
            Keys are encrypted before storage. The client only receives saved/not-saved status flags.
          </p>
        </div>
      </div>

      {blockingCallout && (
        <section className="rounded-3xl border border-warning/20 bg-warning/5 p-5">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-warning" />
            <div className="space-y-2">
              <p className="text-sm font-bold text-warning/90">
                Session creation is blocked until required keys are configured.
              </p>
              {missingItems.length > 0 && (
                <p className="text-sm text-warning/70 font-medium">
                  Missing: {missingItems.join(", ")}.
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {error && (
        <div className="rounded-2xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error font-medium">
          {error}
        </div>
      )}

      {settings.byok.sharedAccessCodeConfigured && (
        <section className="space-y-5 rounded-3xl border border-card-border bg-card p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <h3 className="text-sm font-bold">
                Shared Access Code
              </h3>
              <p className="text-sm text-muted-foreground font-medium">
                Unlock shared Vertex AI credits and server E2B sandbox usage. Without it, use your own E2B and Gemini API keys.
              </p>
            </div>
            <div
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${
                settings.byok.sharedAccessEnabled
                  ? "bg-success/10 text-success"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              {settings.byok.sharedAccessEnabled ? "Unlocked" : "Locked"}
            </div>
          </div>

          <div className="rounded-2xl border border-card-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground font-medium">
            {settings.byok.sharedAccessEnabled
              ? `Shared resources are active for this account.${sharedVertexReady ? " Vertex AI is unlocked." : ""}${sharedE2bReady ? " Server E2B sandbox access is unlocked." : ""}`
              : "Enter the access code to unlock shared server resources for this account."}
          </div>

          <label className="space-y-2 block">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Access Code
            </span>
            <input
              type="password"
              value={accessCode}
              onChange={(event) => setAccessCode(event.target.value)}
              placeholder={
                settings.byok.sharedAccessEnabled
                  ? "Leave blank to keep shared access unlocked"
                  : "Enter access code"
              }
              className="w-full rounded-2xl border border-card-border bg-muted/50 px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent"
            />
          </label>
        </section>
      )}

      <section className="space-y-5 rounded-3xl border border-card-border bg-card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-sm font-bold">
              E2B Sandbox
            </h3>
            <p className="text-sm text-muted-foreground font-medium">
              {sharedE2bReady
                ? "Shared sandbox access is unlocked for this account. Add your own key only if you want to override it."
                : "Required to create desktop sessions unless shared access is unlocked."}
            </p>
          </div>
          <div
            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${
              e2bReady
                ? "bg-success/10 text-success"
                : "bg-muted text-muted-foreground"
            }`}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            {settings.byok.e2bKeySet
              ? "Saved"
              : sharedE2bReady
                ? "Ready via access code"
                : "Not set"}
          </div>
        </div>

        <label className="space-y-2 block">
          <span className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
            E2B API Key
          </span>
          <input
            type="password"
            value={e2bApiKey}
            onChange={(event) => setE2bApiKey(event.target.value)}
            placeholder={
              settings.byok.e2bKeySet
                ? "Leave blank to keep the saved key"
                : sharedE2bReady
                  ? "Shared sandbox access is unlocked; add your own key only if you want to override it"
                  : "Enter your E2B API key"
            }
            className="w-full rounded-2xl border border-card-border bg-muted/50 px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent"
          />
        </label>
      </section>

      <section className="space-y-5 rounded-3xl border border-card-border bg-card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-sm font-bold">
              Gemini Provider
            </h3>
            <p className="text-sm text-muted-foreground font-medium">
              Use your Gemini API key, or unlock the server&apos;s Vertex AI credits with the access code.
            </p>
          </div>
          <div
            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${
              geminiReady
                ? "bg-success/10 text-success"
                : "bg-muted text-muted-foreground"
            }`}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            {geminiReady ? "Ready" : "Needs setup"}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setGeminiProvider("apiKey")}
            className={`rounded-3xl border px-4 py-4 text-left transition ${
              geminiProvider === "apiKey"
                ? "border-accent bg-accent/5"
                : "border-card-border bg-card hover:bg-muted/50"
            }`}
          >
            <div className="space-y-1">
              <p className="text-sm font-bold">
                Gemini API Key
              </p>
              <p className="text-sm text-muted-foreground font-medium">
                Store your own Gemini key for API-based access.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setGeminiProvider("vertex")}
            className={`rounded-3xl border px-4 py-4 text-left transition ${
              geminiProvider === "vertex"
                ? "border-accent bg-accent/5"
                : "border-card-border bg-card hover:bg-muted/50"
            }`}
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-bold">
                <Server className="h-4 w-4 text-muted-foreground" />
                Vertex AI
              </div>
              <p className="text-sm text-muted-foreground font-medium">
                Uses shared server-side Vertex AI. No Gemini API key is required after the access code is accepted.
              </p>
              <p
                className={`text-xs font-bold uppercase tracking-wide ${
                  sharedVertexReady
                    ? "text-success"
                    : settings.byok.vertexConfigured
                      ? "text-warning"
                      : "text-error"
                }`}
              >
                {sharedVertexReady
                  ? "Shared Vertex AI credits are unlocked."
                  : settings.byok.vertexConfigured
                    ? "Enter the access code to unlock shared Vertex AI credits."
                    : "Vertex AI is not configured on the server."}
              </p>
            </div>
          </button>
        </div>

        {geminiProvider === "apiKey" && (
          <label className="space-y-2 block">
            <span className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Gemini API Key
            </span>
            <input
              type="password"
              value={geminiApiKey}
              onChange={(event) => setGeminiApiKey(event.target.value)}
              placeholder={
                settings.byok.geminiKeySet ? "Leave blank to keep the saved key" : "Enter your Gemini API key"
              }
              className="w-full rounded-2xl border border-card-border bg-muted/50 px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent"
            />
          </label>
        )}
      </section>

      <div className="flex flex-col gap-3 border-t border-card-border pt-6 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground font-medium">
          Provider selection is saved immediately with the encrypted key payload.
        </p>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-foreground px-6 py-2.5 text-sm font-bold text-background transition hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving..." : "Save API Settings"}
        </button>
      </div>
    </div>
  );
}
