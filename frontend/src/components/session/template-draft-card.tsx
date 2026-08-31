/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import { Check, Pencil } from "lucide-react";

import { InputPlusMenu } from "@/components/base/input-plus-menu";

import { useToast } from "@/components/toast-provider";
import type { WorkflowTemplateInputField } from "@/lib/message-types";
import { useUpdateTemplateMutation } from "@/lib/queries/templates";
import { queryKeys } from "@/lib/query-keys";
import { useQueryClient } from "@tanstack/react-query";

export type TemplateDraftCardValue = {
  template_id: string;
  status?: "draft" | "published";
  name?: string;
  description?: string;
  instructions?: string;
  input_fields?: WorkflowTemplateInputField[];
  dismissed?: boolean;
};

type Props = {
  value: TemplateDraftCardValue;
  onChange: (patch: Partial<TemplateDraftCardValue>) => void;
};

function cloneFields(fields: WorkflowTemplateInputField[] | undefined) {
  return (fields ?? []).map((field) => ({ ...field }));
}

export function TemplateDraftCard({ value, onChange }: Props) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const updateMutation = useUpdateTemplateMutation();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(value.name ?? "");
  const [description, setDescription] = useState(value.description ?? "");
  const [instructions, setInstructions] = useState(value.instructions ?? "");
  const [inputFields, setInputFields] = useState(cloneFields(value.input_fields));

  const published = value.status === "published";
  const dismissed = Boolean(value.dismissed) && !published;

  const persist = async (payload: {
    name?: string;
    description?: string;
    instructions?: string;
    inputFields?: WorkflowTemplateInputField[];
    status?: "draft" | "published";
  }) => {
    const saved = await updateMutation.mutateAsync({
      templateId: value.template_id,
      payload,
    });
    void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    onChange({
      template_id: saved.template_id,
      status: saved.status ?? payload.status ?? value.status,
      name: saved.name,
      description: saved.description,
      instructions: saved.instructions,
      input_fields: saved.input_fields,
      dismissed: false,
    });
    return saved;
  };

  const handleConfirm = async () => {
    try {
      await persist({ status: "published" });
      toast("Template published. You can run it from Templates.", "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Failed to publish template.", "error");
    }
  };

  const handleSaveEdits = async () => {
    const trimmedName = name.trim();
    const trimmedInstructions = instructions.trim();
    if (!trimmedName || !trimmedInstructions) return;
    try {
      await persist({
        name: trimmedName,
        description: description.trim(),
        instructions: trimmedInstructions,
        inputFields,
      });
      setEditing(false);
      toast("Template updated.", "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Failed to update template.", "error");
    }
  };

  const startEditing = () => {
    setName(value.name ?? "");
    setDescription(value.description ?? "");
    setInstructions(value.instructions ?? "");
    setInputFields(cloneFields(value.input_fields));
    setEditing(true);
  };

  if (dismissed) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600 dark:border-white/10 dark:bg-[#1a1a1c] dark:text-zinc-400">
        Draft saved to Templates as “{value.name || "Untitled template"}”.
      </div>
    );
  }

  return (
    <div className="w-full rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#1a1a1c]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            {published ? "Published template" : "Template draft"}
          </p>
          {!editing ? (
            <h3 className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {value.name || "Untitled template"}
            </h3>
          ) : null}
        </div>
        {!published && !editing ? (
          <button
            type="button"
            onClick={() => onChange({ dismissed: true })}
            className="rounded-full border border-zinc-200 px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/5"
          >
            Dismiss
          </button>
        ) : null}
      </div>

      {editing ? (
        <div className="mt-4 space-y-3">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none focus:border-cyan-500 dark:border-white/10 dark:bg-[#151518] dark:text-zinc-100"
            placeholder="Template name"
          />
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="w-full rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none focus:border-cyan-500 dark:border-white/10 dark:bg-[#151518] dark:text-zinc-100"
            placeholder="Description"
          />
          <div className="relative">
            <textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              rows={8}
              className="w-full rounded-3xl border border-zinc-200 bg-zinc-50 px-4 pb-10 pt-3 text-sm leading-6 outline-none focus:border-cyan-500 dark:border-white/10 dark:bg-[#151518] dark:text-zinc-100"
              placeholder="Instructions"
            />
            <div className="absolute bottom-2 left-2">
              <InputPlusMenu
                showUpload={false}
                showVoice={false}
                onInsertText={(text) => setInstructions((prev) => prev + text)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Input fields</p>
              <button
                type="button"
                onClick={() =>
                  setInputFields((prev) => [
                    ...prev,
                    {
                      key: `field_${prev.length + 1}`,
                      label: `Field ${prev.length + 1}`,
                      placeholder: "",
                      required: false,
                    },
                  ])
                }
                className="text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-300"
              >
                Add field
              </button>
            </div>
            {inputFields.map((field, index) => (
              <div
                key={`${field.key}-${index}`}
                className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-white/10 dark:bg-[#151518]"
              >
                <div className="grid gap-3 md:grid-cols-[1fr_1.2fr_1.2fr_auto]">
                  <input
                    value={field.key}
                    onChange={(event) =>
                      setInputFields((prev) =>
                        prev.map((item, fieldIndex) =>
                          fieldIndex === index ? { ...item, key: event.target.value } : item,
                        ),
                      )
                    }
                    className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                    placeholder="company_name"
                  />
                  <input
                    value={field.label}
                    onChange={(event) =>
                      setInputFields((prev) =>
                        prev.map((item, fieldIndex) =>
                          fieldIndex === index ? { ...item, label: event.target.value } : item,
                        ),
                      )
                    }
                    className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                    placeholder="Company name"
                  />
                  <input
                    value={field.placeholder}
                    onChange={(event) =>
                      setInputFields((prev) =>
                        prev.map((item, fieldIndex) =>
                          fieldIndex === index ? { ...item, placeholder: event.target.value } : item,
                        ),
                      )
                    }
                    className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-[#1f1f23] dark:text-zinc-100"
                    placeholder="Acme Inc."
                  />
                  <div className="flex items-center justify-end gap-2">
                    <label className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(event) =>
                          setInputFields((prev) =>
                            prev.map((item, fieldIndex) =>
                              fieldIndex === index ? { ...item, required: event.target.checked } : item,
                            ),
                          )
                        }
                      />
                      Required
                    </label>
                    <button
                      type="button"
                      onClick={() => setInputFields((prev) => prev.filter((_, fieldIndex) => fieldIndex !== index))}
                      className="rounded-full border border-red-200 px-3 py-1.5 text-xs text-red-600 dark:border-red-500/20 dark:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-full border border-zinc-200 px-4 py-2 text-sm dark:border-white/10 dark:text-zinc-300"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={updateMutation.isPending || !name.trim() || !instructions.trim()}
              onClick={() => void handleSaveEdits()}
              className="rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-white dark:text-zinc-900"
            >
              {updateMutation.isPending ? "Saving..." : "Save edits"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {value.description ? (
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{value.description}</p>
          ) : null}
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-300">
            {value.instructions}
          </p>
          {(value.input_fields ?? []).length > 0 ? (
            <ul className="mt-3 space-y-1 text-sm text-zinc-500">
              {(value.input_fields ?? []).map((field) => (
                <li key={field.key}>
                  {field.label || field.key}
                  {field.required ? " (required)" : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-zinc-500">No extra inputs.</p>
          )}
          {!published ? (
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={startEditing}
                className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-white/10 dark:text-zinc-200 dark:hover:bg-white/5"
              >
                <Pencil className="size-3.5" />
                Edit
              </button>
              <button
                type="button"
                disabled={updateMutation.isPending}
                onClick={() => void handleConfirm()}
                className="inline-flex items-center gap-1.5 rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60"
              >
                <Check className="size-3.5" />
                {updateMutation.isPending ? "Publishing..." : "Confirm"}
              </button>
            </div>
          ) : (
            <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400">
              Published. Run it from the Templates page when you need it.
            </p>
          )}
        </>
      )}
    </div>
  );
}
