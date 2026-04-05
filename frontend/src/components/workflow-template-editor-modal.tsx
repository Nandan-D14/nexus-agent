"use client";

import { useEffect, useReducer } from "react";

import type { WorkflowTemplateInputField } from "@/lib/message-types";
import type { WorkflowTemplateDraft } from "@/lib/workflow-template-utils";

type WorkflowTemplateEditorModalProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  submitLabel: string;
  initialDraft?: WorkflowTemplateDraft;
  initialValue?: WorkflowTemplateDraft;
  isSubmitting?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (draft: WorkflowTemplateDraft) => void | Promise<void>;
};

function cloneInputFields(fields: WorkflowTemplateInputField[]) {
  return fields.map((field) => ({ ...field }));
}

type EditorState = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

type EditorAction =
  | { type: "reset"; draft: WorkflowTemplateDraft | undefined }
  | { type: "setName"; value: string }
  | { type: "setDescription"; value: string }
  | { type: "setInstructions"; value: string }
  | { type: "setInputFields"; value: WorkflowTemplateInputField[] };

function buildEditorState(draft: WorkflowTemplateDraft | undefined): EditorState {
  return {
    name: draft?.name ?? "",
    description: draft?.description ?? "",
    instructions: draft?.instructions ?? "",
    inputFields: cloneInputFields(draft?.inputFields ?? []),
  };
}

function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "reset":
      return buildEditorState(action.draft);
    case "setName":
      return { ...state, name: action.value };
    case "setDescription":
      return { ...state, description: action.value };
    case "setInstructions":
      return { ...state, instructions: action.value };
    case "setInputFields":
      return { ...state, inputFields: action.value };
    default:
      return state;
  }
}

export function WorkflowTemplateEditorModal({
  open,
  title,
  subtitle,
  submitLabel,
  initialDraft,
  initialValue,
  isSubmitting = false,
  error,
  onClose,
  onSubmit,
}: WorkflowTemplateEditorModalProps) {
  const resolvedDraft = initialValue ?? initialDraft;
  const [state, dispatch] = useReducer(editorReducer, buildEditorState(resolvedDraft));

  useEffect(() => {
    if (!open) {
      return;
    }
    dispatch({ type: "reset", draft: resolvedDraft });
  }, [open, resolvedDraft]);

  if (!open) {
    return null;
  }

  const addField = () => {
    dispatch({
      type: "setInputFields",
      value: [
        ...state.inputFields,
      {
        key: `field_${state.inputFields.length + 1}`,
        label: `Field ${state.inputFields.length + 1}`,
        placeholder: "",
        required: false,
      },
      ],
    });
  };

  const updateField = (
    index: number,
    patch: Partial<WorkflowTemplateInputField>,
  ) => {
    dispatch({
      type: "setInputFields",
      value: state.inputFields.map((field, fieldIndex) =>
        fieldIndex === index ? { ...field, ...patch } : field,
      ),
    });
  };

  const removeField = (index: number) => {
    dispatch({
      type: "setInputFields",
      value: state.inputFields.filter((_, fieldIndex) => fieldIndex !== index),
    });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = state.name.trim();
    const trimmedInstructions = state.instructions.trim();
    if (!trimmedName || !trimmedInstructions) {
      return;
    }
    await onSubmit({
      name: trimmedName,
      description: state.description.trim(),
      instructions: trimmedInstructions,
      inputFields: state.inputFields.map((field) => ({
        key: field.key.trim(),
        label: field.label.trim(),
        placeholder: field.placeholder.trim(),
        required: field.required,
      })),
    });
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 px-4 py-8 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-3xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-[#111114]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {title}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {subtitle || "Save the proven flow from this session and reuse it later with manual inputs."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/5"
          >
            Close
          </button>
        </div>

        <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                Template name
              </span>
              <input
                value={state.name}
                onChange={(event) => dispatch({ type: "setName", value: event.target.value })}
                className="w-full rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1a1a1d] dark:text-zinc-100"
                placeholder="Competitor research"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                Description
              </span>
              <input
                value={state.description}
                onChange={(event) =>
                  dispatch({ type: "setDescription", value: event.target.value })
                }
                className="w-full rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1a1a1d] dark:text-zinc-100"
                placeholder="Reusable workflow summary"
              />
            </label>
          </div>

          <label className="block space-y-2">
            <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
              Instructions
            </span>
            <textarea
              value={state.instructions}
              onChange={(event) =>
                dispatch({ type: "setInstructions", value: event.target.value })
              }
              rows={10}
              className="w-full rounded-3xl border border-zinc-200 bg-zinc-50 px-4 py-4 text-sm leading-6 text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1a1a1d] dark:text-zinc-100"
              placeholder="Describe the workflow the agent should reuse."
            />
          </label>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  Manual input fields
                </p>
                <p className="text-xs text-zinc-500">
                  These values will be collected each time the template is run.
                </p>
              </div>
              <button
                type="button"
                onClick={addField}
                className="rounded-full border border-zinc-200 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/5"
              >
                Add field
              </button>
            </div>

            <div className="space-y-3">
              {state.inputFields.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-zinc-300 px-4 py-5 text-sm text-zinc-500 dark:border-white/10">
                  This template does not need extra inputs yet.
                </div>
              ) : (
                state.inputFields.map((field, index) => (
                  <div
                    key={`${field.key}-${index}`}
                    className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-white/10 dark:bg-[#151518]"
                  >
                    <div className="grid gap-3 md:grid-cols-[1fr_1.2fr_1.2fr_auto]">
                      <input
                        value={field.key}
                        onChange={(event) =>
                          updateField(index, { key: event.target.value })
                        }
                        className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                        placeholder="company_name"
                      />
                      <input
                        value={field.label}
                        onChange={(event) =>
                          updateField(index, { label: event.target.value })
                        }
                        className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                        placeholder="Company name"
                      />
                      <input
                        value={field.placeholder}
                        onChange={(event) =>
                          updateField(index, { placeholder: event.target.value })
                        }
                        className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-cyan-500 dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                        placeholder="Acme Inc."
                      />
                      <div className="flex items-center justify-end gap-2">
                        <label className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                          <input
                            type="checkbox"
                            checked={field.required}
                            onChange={(event) =>
                              updateField(index, { required: event.target.checked })
                            }
                          />
                          Required
                        </label>
                        <button
                          type="button"
                          onClick={() => removeField(index)}
                          className="rounded-full border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-red-500/20 dark:text-red-300 dark:hover:bg-red-500/10"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {error ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !state.name.trim() || !state.instructions.trim()}
              className="rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Saving..." : submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
