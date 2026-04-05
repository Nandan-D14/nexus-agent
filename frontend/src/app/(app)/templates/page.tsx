"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Clock, Edit3, Play, Search, Trash2, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";

import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { WorkflowTemplateRunModal } from "@/components/workflow-template-run-modal";
import { useAuth } from "@/lib/auth-context";
import type { WorkflowTemplateData, WorkflowTemplateInputField } from "@/lib/message-types";
import { useWorkflowTemplates } from "@/lib/use-workflow-templates";

type TemplateFormValue = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

const EMPTY_FORM: TemplateFormValue = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

function formatDate(value: string | null | undefined) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleDateString();
}

export default function TemplatesPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { listTemplates, updateTemplate, deleteTemplate, runTemplate, isLoading, error } = useWorkflowTemplates();
  const [templates, setTemplates] = useState<WorkflowTemplateData[]>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [pageError, setPageError] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplateData | null>(null);
  const [editorMode, setEditorMode] = useState<"edit" | null>(null);
  const [runTemplateTarget, setRunTemplateTarget] = useState<WorkflowTemplateData | null>(null);
  const [saveSeedTemplate, setSaveSeedTemplate] = useState<TemplateFormValue>(EMPTY_FORM);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 350);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!user) return;
      const items = await listTemplates(debouncedQuery);
      if (!cancelled) setTemplates(items);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, listTemplates, user]);

  const openEditorForTemplate = (template: WorkflowTemplateData) => {
    setSelectedTemplate(template);
    setSaveSeedTemplate({
      name: template.name,
      description: template.description,
      instructions: template.instructions,
      inputFields: template.input_fields,
    });
    setEditorMode("edit");
  };

  const openRunModal = (template: WorkflowTemplateData) => {
    setRunTemplateTarget(template);
  };

  const closeEditor = () => {
    setEditorMode(null);
    setSelectedTemplate(null);
  };

  const closeRun = () => {
    setRunTemplateTarget(null);
  };

  const refreshTemplates = async () => {
    const items = await listTemplates(debouncedQuery);
    setTemplates(items);
  };

  const handleSaveTemplate = async (value: TemplateFormValue) => {
    setPageError(null);
    const payload = {
      name: value.name,
      description: value.description,
      instructions: value.instructions,
      inputFields: value.inputFields,
    };
    const saved = selectedTemplate
      ? await updateTemplate(selectedTemplate.template_id, payload)
      : null;
    if (!saved) {
      setPageError(error ?? "Failed to save template");
      return;
    }
    await refreshTemplates();
    closeEditor();
  };

  const handleRunTemplate = async (inputs: Record<string, string>) => {
    if (!runTemplateTarget) return;
    setPageError(null);
    const result = await runTemplate(runTemplateTarget.template_id, inputs);
    if (!result) {
      setPageError(error ?? "Failed to run template");
      return;
    }
    try {
      sessionStorage.setItem(
        `nexus.pendingSessionAction:${result.session.session_id}`,
        JSON.stringify({ type: "prompt", text: result.initial_prompt }),
      );
    } catch {
      // Ignore browser storage failures.
    }
    closeRun();
    router.replace(`/session/${result.session.session_id}`);
  };

  const handleDeleteTemplate = async (templateId: string) => {
    if (!confirm("Delete this template?")) return;
    const ok = await deleteTemplate(templateId);
    if (ok) {
      await refreshTemplates();
    } else {
      setPageError(error ?? "Failed to delete template");
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-6 pb-20 h-full flex flex-col text-zinc-900 dark:text-zinc-100">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Templates</h1>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Save successful sessions as reusable workflows and run them again with new inputs.
          </p>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-500" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search templates..."
          className="w-full rounded-3xl border border-zinc-200 dark:border-[#2f2f35] bg-[#f4f4f5] dark:bg-[#212126] py-3 pl-12 pr-4 text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500 outline-none focus:ring-1 focus:ring-zinc-400 dark:focus:ring-zinc-600"
        />
      </div>

      {(pageError || error) && (
        <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {pageError || error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-2">
        {isLoading && templates.length === 0 ? (
          <div className="flex justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-600 border-t-transparent" />
          </div>
        ) : templates.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-3xl border border-dashed border-zinc-300 dark:border-white/10 bg-white/60 dark:bg-white/[0.02] text-sm text-zinc-500 dark:text-zinc-400">
            No templates yet. Save one from a successful session.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {templates.map((template, index) => (
              <motion.div
                key={template.template_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.03 }}
                className="rounded-3xl border border-zinc-200 dark:border-white/5 bg-zinc-50 dark:bg-white/[0.02] p-5 shadow-sm dark:shadow-none"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900">
                        <Workflow className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-semibold">{template.name}</h3>
                        <p className="mt-0.5 text-xs uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                          {template.input_fields.length} inputs
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <p className="mt-4 line-clamp-4 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {template.description || template.instructions}
                </p>

                <div className="mt-4 flex flex-wrap gap-2">
                  {template.input_fields.slice(0, 4).map((field) => (
                    <span
                      key={field.key}
                      className="rounded-full border border-zinc-200 dark:border-white/10 bg-white dark:bg-white/[0.04] px-3 py-1 text-[11px] font-medium text-zinc-600 dark:text-zinc-300"
                    >
                      {field.label}
                    </span>
                  ))}
                </div>

                <div className="mt-5 flex items-center justify-between gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5" />
                    {formatDate(template.updated_at)}
                  </span>
                  <span className="truncate">
                    Source {template.source_session_id}
                  </span>
                </div>

                <div className="mt-5 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => openRunModal(template)}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
                  >
                    <Play className="h-4 w-4" />
                    Run
                  </button>
                  <button
                    type="button"
                    onClick={() => openEditorForTemplate(template)}
                    className="rounded-full border border-zinc-200 dark:border-white/10 px-3 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-white dark:hover:bg-white/5"
                    title="Edit template"
                  >
                    <Edit3 className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteTemplate(template.template_id)}
                    className="rounded-full border border-red-500/20 px-3 py-2 text-sm text-red-500 hover:bg-red-500/10"
                    title="Delete template"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <WorkflowTemplateEditorModal
        open={editorMode === "edit"}
        title="Edit Template"
        subtitle="Adjust the reusable instructions and fields."
        submitLabel="Save Changes"
        initialValue={saveSeedTemplate}
        isSubmitting={isLoading}
        onClose={closeEditor}
        onSubmit={(value) => void handleSaveTemplate(value)}
      />

      <WorkflowTemplateRunModal
        open={Boolean(runTemplateTarget)}
        template={runTemplateTarget}
        isSubmitting={isLoading}
        onClose={closeRun}
        onSubmit={(inputs) => void handleRunTemplate(inputs)}
      />
    </div>
  );
}
