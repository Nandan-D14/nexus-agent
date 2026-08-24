"use client";

import { useEffect, useMemo, useState } from "react";
import {
  RiCheckboxCircleFill,
  RiExternalLinkLine,
  RiKey2Line,
  RiRefreshLine,
} from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { IconButton } from "@/components/base/buttons/icon-button";
import { Chip } from "@/components/base/badges/chip";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { useSettings } from "@/lib/settings-context";
import {
  type E2bSetupInfo,
  type LlmProviderInfo,
  type UserSettingsResponse,
  type UserSettingsUpdatePayload,
  fetchLlmModels,
  fetchUserSettings,
  testLlmConnection,
  updateUserSettings,
} from "@/lib/user-settings";
import { LlmModelComboBox } from "./llm-model-combobox";
import { LlmProviderLogo } from "./llm-provider-logo";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

const SELECT_TRIGGER = "h-8 w-[220px] gap-1 rounded-2lg px-2 py-1.5";

const FALLBACK_E2B: E2bSetupInfo = {
  signupUrl: "https://e2b.dev/auth/sign-up",
  keyUrl: "https://e2b.dev/dashboard?tab=keys",
  docsUrl: "https://www.e2b.dev/docs/api-key",
  steps: [
    "Create an E2B account at e2b.dev/auth/sign-up. New accounts include trial credits.",
    "Open the dashboard and switch to the API keys tab.",
    "Copy your API key. It starts with e2b_.",
    "Paste the key here and save. Do not use the old E2B access-token flow.",
  ],
  notes: "E2B powers the desktop sandbox. A personal API key is required before you can start a session.",
  logoUrl: "/llm-providers/e2b.svg",
  logoInvertInDark: false,
};

function missingLabel(key: string): string {
  if (key === "e2b") return "E2B API key";
  if (key === "llm") return "LLM provider and API key";
  return key;
}

function DocsLink({ href, children }: { href: string; children: string }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-body-2-medium text-text-primary underline-offset-2 hover:underline"
    >
      {children}
      <RiExternalLinkLine className="size-3.5" aria-hidden />
    </a>
  );
}

/**
 * API & Keys settings — required E2B plus preset or custom LLM provider.
 */
export function SettingsApi({
  onSaved,
  forceSetupBanner = false,
}: {
  onSaved?: () => void;
  forceSetupBanner?: boolean;
} = {}) {
  const { refreshByokStatus, applyByokFromSettings } = useSettings();
  const [settings, setSettings] = useState<UserSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [e2bApiKey, setE2bApiKey] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmVisionModel, setLlmVisionModel] = useState("");
  const [llmApiBase, setLlmApiBase] = useState("");
  const [showE2bHelp, setShowE2bHelp] = useState(false);
  const [showLlmHelp, setShowLlmHelp] = useState(true);
  const [remoteModels, setRemoteModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsApiBase, setModelsApiBase] = useState("");
  const [modelsNonce, setModelsNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchUserSettings()
      .then((data) => {
        if (cancelled) return;
        setSettings(data);
        setLlmProvider(data.byok.llmProvider || "");
        setLlmModel(data.byok.llmModel || "");
        setLlmVisionModel(data.byok.llmVisionModel || "");
        setLlmApiBase(data.byok.llmApiBase || "");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load settings.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const providers = settings?.llmProviders ?? [];
  const e2bSetup = settings?.e2bSetup ?? FALLBACK_E2B;
  const selected = useMemo(
    () => providers.find((item) => item.id === llmProvider) ?? null,
    [llmProvider, providers],
  );
  const isCustom = selected?.custom === true || llmProvider === "custom";
  const e2bReady = Boolean(settings?.byok.e2bKeySet);
  const llmReady = Boolean(settings?.byok.llmKeySet && settings.byok.llmProvider);
  const blocking = Boolean(
    settings &&
      (forceSetupBanner || (settings.requireByok && settings.byok.missing.length > 0)),
  );
  const missingItems = (settings?.byok.missing ?? []).map(missingLabel);
  const canFetchModels = Boolean(
    llmProvider &&
      (llmApiKey.trim() || settings?.byok.llmKeySet) &&
      (!isCustom || llmApiBase.trim() || settings?.byok.llmApiBase),
  );
  const modelDescription = modelsLoading
    ? `Fetching every model from ${modelsApiBase || selected?.apiBase || "the provider"}…`
    : modelsError
      ? modelsError
      : remoteModels.length > 0
        ? `${remoteModels.length} models loaded from ${modelsApiBase || selected?.apiBase || "the provider"}`
        : canFetchModels
          ? "Live model list from GET /models on this provider"
          : "Paste an API key to load every model from this provider";

  useEffect(() => {
    if (!llmProvider) {
      setRemoteModels([]);
      return;
    }
    const hasKey = Boolean(llmApiKey.trim() || settings?.byok.llmKeySet);
    const hasBase = !isCustom || Boolean(llmApiBase.trim() || settings?.byok.llmApiBase);
    if (!hasKey || !hasBase) {
      setRemoteModels([]);
      setModelsApiBase("");
      setModelsError(null);
      setModelsLoading(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setModelsLoading(true);
      setModelsError(null);
      fetchLlmModels({
        llmProvider,
        llmApiKey: llmApiKey.trim() || undefined,
        llmApiBase: isCustom ? llmApiBase.trim() || undefined : undefined,
      })
        .then((result) => {
          if (cancelled) return;
          setRemoteModels(result.models);
          setModelsApiBase(result.apiBase);
          setLlmModel((current) => {
            if (current && result.models.includes(current)) return current;
            const preferred = selected?.defaultModel;
            if (preferred && result.models.includes(preferred)) return preferred;
            return result.models[0] || current;
          });
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setRemoteModels([]);
          setModelsApiBase("");
          setModelsError(err instanceof Error ? err.message : "Could not load models from this provider.");
        })
        .finally(() => {
          if (!cancelled) setModelsLoading(false);
        });
    }, 400);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    llmProvider,
    llmApiKey,
    llmApiBase,
    isCustom,
    selected?.defaultModel,
    settings?.byok.llmKeySet,
    settings?.byok.llmApiBase,
    modelsNonce,
  ]);

  const applyProvider = (next: LlmProviderInfo) => {
    setLlmProvider(next.id);
    setLlmModel(next.defaultModel);
    setLlmVisionModel(next.defaultVisionModel || next.defaultModel);
    setLlmApiBase(next.custom ? llmApiBase : "");
    setRemoteModels([]);
    setModelsApiBase("");
    setModelsError(null);
    setShowLlmHelp(true);
  };

  const handleSave = async () => {
    if (!settings) return;
    const nextHasE2b = settings.byok.e2bKeySet || e2bApiKey.trim().length > 0;
    const nextHasLlmKey = settings.byok.llmKeySet || llmApiKey.trim().length > 0;
    const nextModel = llmModel.trim() || selected?.defaultModel || "";
    if (settings.requireByok && !nextHasE2b) {
      setError("An E2B API key is required before you can start a session.");
      return;
    }
    if (settings.requireByok && (!llmProvider || !nextHasLlmKey || !nextModel)) {
      setError("Choose an LLM provider, paste an API key, and set a model before saving.");
      return;
    }
    if (settings.requireByok && isCustom && !llmApiBase.trim() && !settings.byok.llmApiBase) {
      setError("Custom providers need an OpenAI-compatible API base URL ending in /v1.");
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload: UserSettingsUpdatePayload = {
        byok: {
          llmProvider,
          llmModel: nextModel,
          llmVisionModel: (llmVisionModel.trim() || nextModel) || undefined,
        },
      };
      if (e2bApiKey.trim()) payload.byok!.e2bApiKey = e2bApiKey.trim();
      if (llmApiKey.trim()) payload.byok!.llmApiKey = llmApiKey.trim();
      if (isCustom) payload.byok!.llmApiBase = llmApiBase.trim();

      const updated = await updateUserSettings(payload);
      setSettings(updated);
      applyByokFromSettings(updated);
      if (updated.byok.e2bKeySet) setE2bApiKey("");
      if (updated.byok.llmKeySet) setLlmApiKey("");
      setLlmProvider(updated.byok.llmProvider || llmProvider);
      setLlmModel(updated.byok.llmModel || nextModel);
      setLlmVisionModel(updated.byok.llmVisionModel || llmVisionModel);
      setLlmApiBase(updated.byok.llmApiBase || llmApiBase);

      const sentLlmKey = Boolean(llmApiKey.trim());
      const sentE2bKey = Boolean(e2bApiKey.trim());
      if (sentLlmKey && !updated.byok.llmKeySet) {
        setError("The LLM API key could not be saved. Paste it again and save.");
        return;
      }
      if (sentE2bKey && !updated.byok.e2bKeySet) {
        setError("The E2B API key could not be saved. Paste it again and save.");
        return;
      }
      if (updated.requireByok && updated.byok.missing.length > 0) {
        setError(
          `Saved, but still needed: ${updated.byok.missing.map(missingLabel).join(", ")}.`,
        );
      } else {
        setNotice("API keys saved. You can start a session.");
        onSaved?.();
      }
      await refreshByokStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await testLlmConnection({
        llmProvider: llmProvider || undefined,
        llmApiKey: llmApiKey.trim() || undefined,
        llmModel: llmModel.trim() || undefined,
        llmVisionModel: llmVisionModel.trim() || undefined,
        llmApiBase: isCustom ? llmApiBase.trim() || undefined : undefined,
      });
      setNotice(`Connected. Provider accepted model ${result.model}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "LLM connection test failed.");
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex w-full items-center justify-center py-16">
        <span className="text-body-2-regular text-text-secondary">Loading…</span>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      {blocking && (
        <div
          role="status"
          className="rounded-2lg border border-status-yellow-text/20 bg-status-yellow-background px-3 py-2 text-body-2-regular text-status-yellow-text"
        >
          Session creation is blocked until required keys are configured
          {missingItems.length > 0 ? `: ${missingItems.join(", ")}.` : "."}
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {error}
        </div>
      )}

      {notice && (
        <div
          role="status"
          className="rounded-2lg border border-status-lime-text/20 bg-status-lime-background px-3 py-2 text-body-2-regular text-status-lime-text"
        >
          {notice}
        </div>
      )}

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>E2B sandbox (required)</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="E2B API Key"
            description={e2bSetup.notes || "Powers the agent desktop sandbox"}
          >
            <div className="flex shrink-0 items-center gap-2">
              <LlmProviderLogo
                src={e2bSetup.logoUrl || "/llm-providers/e2b.svg"}
                name="E2B"
                invertInDark={Boolean(e2bSetup.logoInvertInDark)}
              />
              {e2bReady && (
                <Chip variant="caption" color="lime" className="inline-flex items-center gap-0.5">
                  <RiCheckboxCircleFill className="size-3" aria-hidden />
                  Saved
                </Chip>
              )}
              <Input
                size="small"
                type="password"
                autoComplete="off"
                aria-label="E2B API Key"
                leadingIcon={RiKey2Line}
                value={e2bApiKey}
                onChange={setE2bApiKey}
                placeholder={settings?.byok.e2bKeySet ? "••••••••••••••••" : "e2b_…"}
                className="w-[202px] shrink-0"
              />
            </div>
          </SettingsRow>
          <div className="flex flex-col gap-2 py-2.5 pr-2.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <DocsLink href={e2bSetup.signupUrl}>Create account</DocsLink>
              <DocsLink href={e2bSetup.keyUrl}>Get API key</DocsLink>
              <DocsLink href={e2bSetup.docsUrl}>E2B docs</DocsLink>
              <button
                type="button"
                className="text-body-2-medium text-text-secondary hover:text-text-primary"
                onClick={() => setShowE2bHelp((open) => !open)}
              >
                {showE2bHelp ? "Hide steps" : "How to get this key"}
              </button>
            </div>
            {showE2bHelp && (
              <ol className="list-decimal space-y-1 pl-4 text-body-2-regular text-text-secondary">
                {e2bSetup.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            )}
          </div>
        </SettingsCard>
      </div>

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Language model (required)</SettingsSectionLabel>
        <SettingsCard>
          <SettingsRow
            label="Provider"
            description={selected?.description || "Choose an OpenAI-compatible provider"}
          >
            <div className="flex shrink-0 items-center gap-2">
              {llmReady && settings?.byok.llmProvider === llmProvider && (
                <Chip variant="caption" color="lime" className="inline-flex items-center gap-0.5">
                  <RiCheckboxCircleFill className="size-3" aria-hidden />
                  Saved
                </Chip>
              )}
              <Select
                aria-label="LLM provider"
                placeholder="Select a provider"
                selectedKey={llmProvider || null}
                onSelectionChange={(key) => {
                  const next = providers.find((item) => item.id === String(key || ""));
                  if (next) applyProvider(next);
                }}
                triggerClassName={SELECT_TRIGGER}
                popoverClassName="z-[200] w-[280px]"
                renderValue={() =>
                  selected ? (
                    <span className="flex min-w-0 items-center gap-1.5">
                      <LlmProviderLogo
                        src={selected.logoUrl}
                        name={selected.name}
                        invertInDark={Boolean(selected.logoInvertInDark)}
                      />
                      <span className="truncate">{selected.name}</span>
                    </span>
                  ) : (
                    <span className="text-text-tertiary">Select a provider</span>
                  )
                }
              >
                {providers.map((provider) => (
                  <SelectItem key={provider.id} id={provider.id} textValue={provider.name}>
                    <span className="flex min-w-0 items-center gap-2">
                      <LlmProviderLogo
                        src={provider.logoUrl}
                        name={provider.name}
                        invertInDark={Boolean(provider.logoInvertInDark)}
                      />
                      <span className="truncate">{provider.name}</span>
                    </span>
                  </SelectItem>
                ))}
              </Select>
            </div>
          </SettingsRow>

          <SettingsRow label="API key" description="Encrypted before storage. The client never reads it back.">
            <Input
              size="small"
              type="password"
              autoComplete="off"
              aria-label="LLM API Key"
              leadingIcon={RiKey2Line}
              value={llmApiKey}
              onChange={setLlmApiKey}
              placeholder={llmReady ? "••••••••••••••••" : "Paste API key"}
              className="w-[220px] shrink-0"
            />
          </SettingsRow>

          {isCustom && (
            <SettingsRow
              label="API base URL"
              description="OpenAI-compatible endpoint, usually ending in /v1"
            >
              <Input
                size="small"
                aria-label="LLM API base URL"
                value={llmApiBase}
                onChange={setLlmApiBase}
                placeholder="https://api.example.com/v1"
                className="w-[220px] shrink-0"
              />
            </SettingsRow>
          )}

          <SettingsRow
            label="Model"
            description={selected?.visionWarning || modelDescription}
          >
            <div className="flex shrink-0 items-center gap-1.5">
              <LlmModelComboBox
                models={remoteModels}
                value={llmModel}
                onChange={(next) => {
                  setLlmModel(next);
                  if (
                    !llmVisionModel ||
                    llmVisionModel === llmModel ||
                    llmVisionModel === selected?.defaultVisionModel
                  ) {
                    setLlmVisionModel(
                      next === selected?.defaultModel
                        ? selected?.defaultVisionModel || next
                        : next,
                    );
                  }
                }}
                loading={modelsLoading}
                disabled={!llmProvider}
                placeholder={canFetchModels ? "Search models" : "Paste a key first"}
              />
              <IconButton
                size="small"
                icon={RiRefreshLine}
                aria-label="Refresh models"
                disabled={!canFetchModels || modelsLoading}
                onClick={() => setModelsNonce((value) => value + 1)}
              />
            </div>
          </SettingsRow>

          {isCustom && (
            <SettingsRow
              label="Vision model"
              description="Optional. Defaults to the chat model. Needs image input for desktop screenshots."
            >
              <Input
                size="small"
                aria-label="Vision model"
                value={llmVisionModel}
                onChange={setLlmVisionModel}
                placeholder={llmModel || "same as chat model"}
                className="w-[202px] shrink-0"
              />
            </SettingsRow>
          )}

          {selected && (
            <div className="flex flex-col gap-2 py-2.5 pr-2.5">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <DocsLink href={selected.signupUrl}>Sign up</DocsLink>
                <DocsLink href={selected.keyUrl}>Get API key</DocsLink>
                <DocsLink href={selected.docsUrl}>Docs</DocsLink>
                <button
                  type="button"
                  className="text-body-2-medium text-text-secondary hover:text-text-primary"
                  onClick={() => setShowLlmHelp((open) => !open)}
                >
                  {showLlmHelp ? "Hide steps" : "How to get this key"}
                </button>
              </div>
              {showLlmHelp && (
                <div className="flex flex-col gap-2">
                  <ol className="list-decimal space-y-1 pl-4 text-body-2-regular text-text-secondary">
                    {selected.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  {selected.notes ? (
                    <p className="text-body-2-regular text-text-secondary">{selected.notes}</p>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </SettingsCard>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size="small"
          className="w-fit"
          disabled={saving || !settings}
          onClick={() => void handleSave()}
        >
          {saving ? "Saving…" : "Save API Settings"}
        </Button>
        <Button
          variant="secondary"
          size="small"
          className="w-fit"
          disabled={testing || !llmProvider}
          onClick={() => void handleTest()}
        >
          {testing ? "Testing…" : "Test connection"}
        </Button>
      </div>
    </div>
  );
}
