/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ChevronDown, Search } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";
import { TemplateCard } from "@/components/templates/template-card";
import { TemplatesSkeleton } from "@/components/templates/templates-skeleton";
import { useToast } from "@/components/toast-provider";
import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { WorkflowTemplateRunModal } from "@/components/workflow-template-run-modal";
import { sessionPath } from "@/lib/app-paths";
import type { WorkflowTemplateData } from "@/lib/message-types";
import { useTemplatesQuery } from "@/lib/queries/templates";
import {
  TEMPLATE_FILTERS,
  filterTemplates,
  isPublishedTemplate,
  searchTemplates,
  type TemplateFilterId,
} from "@/lib/templates";
import { useWorkflowTemplates } from "@/lib/use-workflow-templates";
import {
  queuePendingSessionPrompt,
  type WorkflowTemplateDraft,
} from "@/lib/workflow-template-utils";

const EMPTY_FORM: WorkflowTemplateDraft = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

const toolbarControl =
  "inline-flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-sm text-zinc-800 transition-colors hover:bg-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700 dark:focus-visible:ring-zinc-600";

const toolbarIconControl =
  "inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg bg-zinc-100 text-zinc-800 transition-colors hover:bg-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700 dark:focus-visible:ring-zinc-600";

export function TemplatesView() {
  const router = useRouter();
  const { toast } = useToast();
  const {
    createTemplate,
    updateTemplate,
    deleteTemplate,
    runTemplate,
    isLoading,
    error,
  } = useWorkflowTemplates();
  const templatesQuery = useTemplatesQuery();
  const templates = templatesQuery.data ?? [];
  const loading = templatesQuery.isLoading;
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [filter, setFilter] = useState<TemplateFilterId>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const lastToastedPageErrorRef = useRef<string | null>(null);
  const lastToastedErrorRef = useRef<string | null>(null);

  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplateData | null>(null);
  const [editorMode, setEditorMode] = useState<"create" | "edit" | null>(null);
  const [runTemplateTarget, setRunTemplateTarget] = useState<WorkflowTemplateData | null>(null);
  const [saveSeedTemplate, setSaveSeedTemplate] = useState<WorkflowTemplateDraft>(EMPTY_FORM);

  useEffect(() => {
    if (pageError && pageError !== lastToastedPageErrorRef.current) {
      lastToastedPageErrorRef.current = pageError;
      toast(pageError, "error");
    } else if (!pageError) {
      lastToastedPageErrorRef.current = null;
    }
  }, [pageError, toast]);

  useEffect(() => {
    if (error && error !== lastToastedErrorRef.current) {
      lastToastedErrorRef.current = error;
      toast(error, "error");
    } else if (!error) {
      lastToastedErrorRef.current = null;
    }
  }, [error, toast]);

  useEffect(() => {
    const handle = window.setTimeout(() => setSearchQuery(searchInput.trim()), 400);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  const visibleTemplates = useMemo(
    () => filterTemplates(searchTemplates(templates, searchQuery), filter),
    [filter, searchQuery, templates],
  );

  const filterLabel = TEMPLATE_FILTERS.find((item) => item.id === filter)?.label ?? "All";

  const openCreateEditor = () => {
    setSelectedTemplate(null);
    setSaveSeedTemplate(EMPTY_FORM);
    setEditorMode("create");
  };

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

  const closeEditor = () => {
    setEditorMode(null);
    setSelectedTemplate(null);
    setSaveSeedTemplate(EMPTY_FORM);
  };

  const closeRun = () => {
    setRunTemplateTarget(null);
  };

  const handleSaveTemplate = async (value: WorkflowTemplateDraft) => {
    setPageError(null);
    if (editorMode === "create") {
      const saved = await createTemplate({
        name: value.name,
        description: value.description,
        instructions: value.instructions,
        inputFields: value.inputFields,
      });
      if (!saved) {
        setPageError(error ?? "Failed to create template");
        return;
      }
      closeEditor();
      return;
    }
    if (!selectedTemplate) return;
    const saved = await updateTemplate(selectedTemplate.template_id, {
      name: value.name,
      description: value.description,
      instructions: value.instructions,
      inputFields: value.inputFields,
    });
    if (!saved) {
      setPageError(error ?? "Failed to save template");
      return;
    }
    closeEditor();
  };

  const handleRunTemplate = async (inputs: Record<string, string>) => {
    if (!runTemplateTarget) return;
    if (!isPublishedTemplate(runTemplateTarget)) {
      setPageError("Publish this template before running it.");
      return;
    }
    setPageError(null);
    const result = await runTemplate(runTemplateTarget.template_id, inputs);
    if (!result) {
      setPageError(error ?? "Failed to run template");
      return;
    }
    try {
      queuePendingSessionPrompt(result.session.session_id, result.initial_prompt);
    } catch {
      // Ignore browser storage failures.
    }
    closeRun();
    router.replace(sessionPath(result.session.session_id));
  };

  const handleDeleteTemplate = async (templateId: string) => {
    if (!confirm("Delete this template?")) return;
    const ok = await deleteTemplate(templateId);
    if (!ok) {
      setPageError(error ?? "Failed to delete template");
    }
  };

  const emptyMessage = searchQuery
    ? "No templates match your search"
    : filter !== "all"
      ? "No templates in this filter"
      : "No templates yet";

  const fetchFailed =
    !loading && templates.length === 0 && Boolean(templatesQuery.isError || error || pageError);

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
      {loading ? (
        <TemplatesSkeleton />
      ) : (
        <>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3">
            <h1 className="min-w-0 font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
              Templates
            </h1>
            <div className="flex items-center gap-2.5">
              {searchOpen ? (
                <div className="relative">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-zinc-500" />
                  <input
                    ref={searchInputRef}
                    type="search"
                    placeholder="Search"
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key !== "Escape") return;
                      if (searchInput) {
                        setSearchInput("");
                        return;
                      }
                      setSearchOpen(false);
                    }}
                    className="h-9 w-44 rounded-lg border-0 bg-zinc-100 py-0 pr-3 pl-8 text-sm text-zinc-900 placeholder-zinc-500 outline-none ring-0 focus:ring-2 focus:ring-zinc-400 sm:w-56 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:ring-zinc-600"
                  />
                </div>
              ) : (
                <button
                  type="button"
                  aria-label="Search templates"
                  onClick={() => setSearchOpen(true)}
                  className={toolbarIconControl}
                >
                  <Search className="size-4" />
                </button>
              )}

              <Dropdown isOpen={filterOpen} onOpenChange={setFilterOpen}>
                <DropdownTrigger aria-label={`Filter by ${filterLabel}`} className={toolbarControl}>
                  <span className="text-zinc-500 dark:text-zinc-400">Filter by</span>
                  <span className="font-medium text-zinc-900 dark:text-white">{filterLabel}</span>
                  <ChevronDown className="size-3.5 text-zinc-500" />
                </DropdownTrigger>
                <DropdownPopover aria-label="Filter templates" placement="bottom end" className="w-44">
                  <DropdownGroup>
                    {TEMPLATE_FILTERS.map((item) => (
                      <DropdownItem
                        key={item.id}
                        selected={filter === item.id}
                        onSelect={() => {
                          setFilter(item.id);
                          setFilterOpen(false);
                        }}
                      >
                        {item.label}
                      </DropdownItem>
                    ))}
                  </DropdownGroup>
                </DropdownPopover>
              </Dropdown>

              <button
                type="button"
                aria-label="New template"
                onClick={openCreateEditor}
                className="inline-flex h-9 items-center justify-center rounded-lg bg-zinc-900 px-3.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100 dark:focus-visible:ring-zinc-500"
              >
                New
              </button>
            </div>
          </div>

          <div className="mt-10 min-h-0 flex-1 overflow-y-auto pr-1">
            {fetchFailed ? (
              <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
                <AlertCircle className="size-5 shrink-0" />
                <p>{(templatesQuery.error instanceof Error && templatesQuery.error.message) || error || pageError}</p>
              </div>
            ) : visibleTemplates.length === 0 ? (
              <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-zinc-300 font-mono text-sm text-zinc-500 uppercase dark:border-white/10">
                {emptyMessage}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {visibleTemplates.map((template, index) => (
                  <TemplateCard
                    key={template.template_id}
                    template={template}
                    index={index}
                    onRun={() => {
                      if (!isPublishedTemplate(template)) return;
                      setRunTemplateTarget(template);
                    }}
                    onEdit={() => openEditorForTemplate(template)}
                    onDelete={() => void handleDeleteTemplate(template.template_id)}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <WorkflowTemplateEditorModal
        open={editorMode === "create" || editorMode === "edit"}
        title={editorMode === "create" ? "New Template" : "Edit Template"}
        subtitle={
          editorMode === "create"
            ? "Create a reusable workflow with instructions and input fields."
            : "Adjust the reusable instructions and fields."
        }
        submitLabel={editorMode === "create" ? "Create Template" : "Save Changes"}
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
