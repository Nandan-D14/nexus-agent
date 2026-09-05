/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { InputPlusMenu } from "@/components/base/input-plus-menu";

export function SkillField({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-input-border bg-input-bg px-3.5 py-2 text-sm text-text-primary outline-none placeholder:text-text-placeholder focus:border-border-button-hover"
      />
      {hint ? <span className="text-[11px] text-text-tertiary">{hint}</span> : null}
    </label>
  );
}

export function SkillTextArea({
  label,
  value,
  onChange,
  placeholder,
  rows = 6,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <div className="block space-y-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">{label}</span>
      <div className="relative">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="custom-scrollbar w-full resize-none rounded-lg border border-input-border bg-input-bg px-3.5 pb-10 pt-2 text-sm text-text-primary outline-none placeholder:text-text-placeholder focus:border-border-button-hover"
        />
        <div className="absolute bottom-2 left-2">
          <InputPlusMenu
            showUpload={false}
            showVoice={false}
            onInsertText={(text) => onChange(value + text)}
          />
        </div>
      </div>
    </div>
  );
}
