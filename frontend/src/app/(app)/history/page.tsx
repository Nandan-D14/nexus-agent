"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertCircle,
  Clock,
  Filter,
  MessageSquare,
  Search,
  Trash2,
  Workflow,
} from "lucide-react";

import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import type { HandoffSummary, WorkflowTemplateInputField } from "@/lib/message-types";
import { useWorkflowTemplates } from "@/lib/use-workflow-templates";

interface HistorySession {
  session_id: string;
  title: string;
  status: string;
  created_at: string;
  ended_at: string | null;
  message_count: number;
  summary?: string | null;
  handoff_summary?: HandoffSummary | null;
  can_continue_workspace?: boolean;
  can_continue_conversation?: boolean;
  has_artifacts?: boolean;
  resume_state?: string | null;
  context_packet?: { summary?: string | null } | null;
  current_run_id?: string | null;
  run_status?: string | null;
}

type TemplateFormValue = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

const EMPTY_TEMPLATE: TemplateFormValue = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

function summaryPreview(session: HistorySession) {
  return (
    session.handoff_summary?.preview ||
    session.summary ||
    "Reusable handoff will be generated when the session is resumed."
  );
}

function buildTemplateSeed(session: HistorySession): TemplateFormValue {
  const headline =
    session.handoff_summary?.headline ||
    session.title ||
    "Workflow template";
  const description =
    session.handoff_summary?.preview ||
    session.summary ||
    session.context_packet?.summary ||
    "";
  const instructions =
    session.handoff_summary?.preview ||
    session.context_packet?.summary ||
    session.summary ||
    "Describe the reusable workflow instructions here.";

  return {
    name: headline,
    description,
    instructions,
    inputFields: [],
  };
}

export default function HistoryPage() {
  const { user } = useAuth();
  const { saveSessionAsTemplate, isLoading: templateLoading, error: templateError } = useWorkflowTemplates();
  const [sessions, setSessions] = useState<HistorySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [templateSource, setTemplateSource] = useState<HistorySession | null>(null);
  const [templateSeed, setTemplateSeed] = useState<TemplateFormValue>(EMPTY_TEMPLATE);

  const fetchHistory = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      let path = "/api/v1/history?limit=50";
      if (searchQuery) path += `&q=${encodeURIComponent(searchQuery)}`;
      if (statusFilter !== "all") path += `&status=${statusFilter}`;

      const res = await authenticatedFetch(path);
      if (!res.ok) throw new Error(await parseApiError(res));
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch history");
    } finally {
      setLoading(false);
    }
  }, [searchQuery, statusFilter, user]);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      void fetchHistory();
    }, 500);
    return () => clearTimeout(delayDebounceFn);
  }, [fetchHistory]);

  const deleteSession = async (sessionId: string) => {
    if (!confirm("Are you sure you want to delete this session?")) return;
    try {
      const res = await authenticatedFetch(`/sessions/${sessionId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      } else {
        throw new Error(await parseApiError(res));
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to delete session");
    }
  };

  const openTemplateModal = (session: HistorySession) => {
    setTemplateSource(session);
    setTemplateSeed(buildTemplateSeed(session));
  };

  const closeTemplateModal = () => {
    setTemplateSource(null);
    setTemplateSeed(EMPTY_TEMPLATE);
  };

  const handleTemplateSubmit = async (value: TemplateFormValue) => {
    if (!templateSource) return;
    const saved = await saveSessionAsTemplate(templateSource.session_id, {
      name: value.name,
      description: value.description,
      instructions: value.instructions,
      inputFields: value.inputFields,
    });
    if (saved) {
      closeTemplateModal();
      await fetchHistory();
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-6 pb-20 h-full flex flex-col text-zinc-900 dark:text-zinc-100">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            Mission History
          </h1>
          <p className="text-sm text-zinc-500 mt-2">
            Open any prior thread and continue in place without duplicating the session.
          </p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 shrink-0">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search sessions and summaries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#f4f4f5] dark:bg-[#212126] border border-zinc-200 dark:border-[#2f2f35] rounded-3xl py-3 pl-12 pr-4 text-zinc-900 dark:text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:focus:ring-zinc-600 transition-colors shadow-sm"
          />
        </div>
        <div className="relative shrink-0">
          <Filter className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full sm:w-48 appearance-none bg-[#f4f4f5] dark:bg-[#212126] border border-zinc-200 dark:border-[#2f2f35] rounded-3xl py-3 pl-10 pr-10 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:focus:ring-zinc-600 shadow-sm"
          >
            <option value="all" className="bg-white dark:bg-zinc-900">All Statuses</option>
            <option value="ready" className="bg-white dark:bg-zinc-900">Ready</option>
            <option value="active" className="bg-white dark:bg-zinc-900">Active</option>
            <option value="ended" className="bg-white dark:bg-zinc-900">Ended</option>
            <option value="error" className="bg-white dark:bg-zinc-900">Error</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-600 dark:text-red-400">
          <AlertCircle className="w-5 h-5" />
          <p>{error}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-3 pr-2 min-h-0">
        {loading ? (
          <div className="flex justify-center p-10">
            <div className="w-8 h-8 border-4 border-cyan-600 dark:border-cyan-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="h-64 rounded-2xl border border-zinc-300 dark:border-white/10 border-dashed flex items-center justify-center text-zinc-500 font-mono text-sm uppercase">
            No sessions found matching criteria
          </div>
        ) : (
          sessions.map((session, i) => (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              key={session.session_id}
              className="group bg-zinc-50 dark:bg-white/[0.02] border border-zinc-200 dark:border-white/5 rounded-2xl p-5 hover:bg-zinc-100 dark:hover:bg-white/[0.04] transition-colors shadow-sm dark:shadow-none"
            >
              <div className="flex flex-col gap-4">
                <div className="flex flex-col md:flex-row md:items-start gap-4 justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="text-foreground font-bold truncate text-base">
                        {session.title || "Untitled Session"}
                      </h3>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${
                        session.can_continue_workspace
                          ? "bg-cyan-100 dark:bg-cyan-500/20 text-cyan-700 dark:text-cyan-300"
                          : session.status === "error"
                            ? "bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400"
                            : "bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                      }`}>
                        {session.can_continue_workspace ? "exact resume" : session.can_continue_conversation ? "thread ready" : session.status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                      {summaryPreview(session)}
                    </p>
                    <div className="flex items-center gap-4 text-xs font-mono text-zinc-500 mt-3 flex-wrap">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        {new Date(session.created_at).toLocaleDateString()}
                      </span>
                      <span className="flex items-center gap-1">
                        <MessageSquare className="w-3.5 h-3.5" />
                        {session.message_count} msgs
                      </span>
                      {session.resume_state ? (
                        <span className="uppercase tracking-widest text-[10px]">{session.resume_state}</span>
                      ) : null}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 flex-wrap">
                    <button
                      onClick={() => openTemplateModal(session)}
                      className="inline-flex items-center gap-2 rounded-full border border-zinc-300 dark:border-white/10 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-white/80 dark:hover:bg-white/5"
                    >
                      <Workflow className="w-4 h-4" />
                      Save as Template
                    </button>
                    <Link
                      href={`/session/${session.session_id}?continue=1`}
                      className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
                    >
                      Continue Here
                    </Link>
                    <Link
                      href={`/session/${session.session_id}`}
                      className="inline-flex items-center gap-2 rounded-full border border-zinc-300 dark:border-white/10 px-4 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-white/80 dark:hover:bg-white/5"
                    >
                      View Transcript
                    </Link>
                    <button
                      onClick={() => void deleteSession(session.session_id)}
                      className="p-2 text-zinc-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer"
                      title="Delete Session"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {session.handoff_summary?.recommended_next_step ? (
                  <div className="rounded-xl border border-zinc-200 dark:border-white/10 bg-white/70 dark:bg-white/[0.03] px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-500">
                      Recommended Next Step
                    </p>
                    <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                      {session.handoff_summary.recommended_next_step}
                    </p>
                  </div>
                ) : null}
              </div>
            </motion.div>
          ))
        )}
      </div>

      <WorkflowTemplateEditorModal
        open={Boolean(templateSource)}
        title="Save as Template"
        subtitle="Save this successful session as a reusable workflow."
        submitLabel="Save Template"
        initialValue={templateSeed}
        isSubmitting={templateLoading}
        onClose={closeTemplateModal}
        onSubmit={(value) => void handleTemplateSubmit(value)}
      />

      {(templateError || error) && (
        <div className="fixed bottom-4 right-4 max-w-md rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400 shadow-lg">
          {templateError || error}
        </div>
      )}
    </div>
  );
}
