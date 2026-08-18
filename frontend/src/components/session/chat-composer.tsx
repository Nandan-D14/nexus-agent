/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import {
  ArrowUp,
  BookOpen,
  ChevronDown,
  Image as ImageIcon,
  Loader2,
  Mic,
  Monitor,
  Paperclip,
  Plus,
  Square,
  X,
} from "lucide-react";
import { ToolPickerPanel } from "./tool-picker";
import type { SessionConnector } from "@/lib/session-utils";
import type { UploadedInputFile } from "@/lib/message-types";
import { authenticatedFetch } from "@/lib/api-client";
import { builtInPaletteItems, type ToolPaletteItem } from "@/lib/tool-catalog";
import { cx } from "@/utils/cx";

type Props = {
  textInput: string;
  onChangeText: (text: string) => void;
  onSubmitText: () => void;
  onOpenFilePicker: (kind?: "image" | "file") => void;
  uploadDisabled: boolean;
  uploadedFiles: UploadedInputFile[];
  onRemoveFile: (path: string) => void;
  onToggleMic: () => void;
  isRecording: boolean;
  voiceStatus: string;
  phase: string;
  isLoading: boolean;
  isUploadingFile: boolean;
  onStopAgent: () => void;
  onShowDesktop: () => void;
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  onToggleAllConnectors: (ids: string[]) => void;
  selectedToolIds: string[];
  onToggleTool: (id: string) => void;
  onToggleAllTools: (ids: string[]) => void;
  connectorsLoading?: boolean;
  onRefreshTools?: () => void;
  isLanding?: boolean;
  inputRef?: React.RefObject<HTMLDivElement | null>;
  onEnhance?: (prompt: string, signal?: AbortSignal) => Promise<string>;
};

type AgentSkill = {
  skill_id: string;
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
  source: "built_in" | "user";
  enabled: boolean;
};

type Phase = "idle" | "enhancing" | "enhanced";

const MOCK_ENHANCED =
  "This is an example prompt — rewritten to be clear and specific: state the goal, add the relevant context and constraints, define the expected output format and tone, and note any assumptions. Ask a clarifying question first if key details are missing.";

async function mockEnhance(prompt: string, signal?: AbortSignal): Promise<string> {
  await new Promise((r) => setTimeout(r, 2500));
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return MOCK_ENHANCED;
}

const escapeHtml = (str: string) =>
  str.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] ?? c));

/** Serialize editor DOM so skill pills emit `/{skill_id}` for the agent. */
function editorPlainText(editor: HTMLElement): string {
  let result = "";
  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent ?? "";
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node as HTMLElement;
    if (el.dataset.skill) {
      result += `/${el.dataset.skill}`;
      return;
    }
    if (el.dataset.tool) {
      result += `@[${el.dataset.tool}]`;
      return;
    }
    if (el.tagName === "BR") {
      result += "\n";
      return;
    }
    el.childNodes.forEach(walk);
  };
  editor.childNodes.forEach(walk);
  return result.replace(/\u00A0/g, " ");
}

export function ChatComposer({
  textInput,
  onChangeText,
  onSubmitText,
  onOpenFilePicker,
  uploadDisabled,
  uploadedFiles,
  onRemoveFile,
  onToggleMic,
  isRecording,
  voiceStatus,
  phase,
  isLoading,
  isUploadingFile,
  onStopAgent,
  onShowDesktop,
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  onToggleAllConnectors,
  selectedToolIds,
  onToggleTool,
  onToggleAllTools,
  connectorsLoading = false,
  onRefreshTools,
  isLanding = false,
  inputRef: externalInputRef,
  onEnhance = mockEnhance,
}: Props) {
  const localEditorRef = useRef<HTMLDivElement>(null);
  const editorRef = externalInputRef || localEditorRef;
  const frameRef = useRef<HTMLDivElement>(null);
  const plusRef = useRef<HTMLDivElement>(null);

  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [menuPlacement, setMenuPlacement] = useState<"top" | "bottom">("top");
  const [menuMaxHeight, setMenuMaxHeight] = useState(480);

  const [enhancePhase, setEnhancePhase] = useState<Phase>("idle");
  const [pillMounted, setPillMounted] = useState(false);
  const [pillExiting, setPillExiting] = useState(false);

  const [slashOpen, setSlashOpen] = useState(false);
  const [slashQuery, setSlashQuery] = useState("");
  const [slashIndex, setSlashIndex] = useState(0);
  const [slashKeyboard, setSlashKeyboard] = useState(false);

  const [atOpen, setAtOpen] = useState(false);
  const [atQuery, setAtQuery] = useState("");
  const [atIndex, setAtIndex] = useState(0);

  const preEnhanceHTML = useRef("");
  const pendingHTML = useRef<string | null>(null);
  const flipFrom = useRef<number | null>(null);
  const savedRange = useRef<Range | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const syncingFromParent = useRef(false);

  const slashOpenRef = useRef(false);
  const slashIndexRef = useRef(0);
  const slashResultsRef = useRef<AgentSkill[]>([]);
  const slashQueryRef = useRef("");
  const slashTokenRef = useRef<{ node: Text; start: number; end: number } | null>(null);
  const ignoreHoverRef = useRef(false);
  const applySlashRef = useRef<(id: string) => void>(() => {});
  const slashKeyLock = useRef(false);

  const atTokenRef = useRef<{ node: Text; start: number; end: number } | null>(null);

  const hasText = textInput.trim().length > 0;
  const enhancing = enhancePhase === "enhancing";
  const isBusy = phase === "thinking" || phase === "acting";
  const sendActive = hasText && !enhancing && !isLoading && !isUploadingFile;
  const showEnhancePill = hasText && !enhancing && !isBusy;

  const allTools: ToolPaletteItem[] = [
    ...builtInPaletteItems(),
    ...availableConnectors
      .filter((conn) => conn.connection_id !== "system" && conn.enabled)
      .map((conn) => ({
        id: conn.connection_id,
        name: conn.name,
        description: `Access connector: ${conn.provider}`,
        category: "Integration" as const,
      })),
  ];

  const slashResults = skills.filter((skill) => {
    const needle = slashQuery.trim().toLowerCase();
    if (!needle) return true;
    return (
      skill.name.toLowerCase().includes(needle) ||
      skill.skill_id.toLowerCase().includes(needle) ||
      (skill.description || "").toLowerCase().includes(needle)
    );
  });

  const atResults = allTools.filter((tool) => {
    const needle = atQuery.trim().toLowerCase();
    if (!needle) return true;
    return (
      tool.name.toLowerCase().includes(needle) ||
      tool.id.toLowerCase().includes(needle) ||
      tool.description.toLowerCase().includes(needle)
    );
  });

  const selectionCount = selectedToolIds.length + selectedConnectorIds.length;

  slashOpenRef.current = slashOpen;
  slashIndexRef.current = slashIndex;
  slashResultsRef.current = slashResults;

  useEffect(() => {
    async function loadSkills() {
      try {
        const response = await authenticatedFetch("/api/v1/skills");
        if (response.ok) {
          const body = (await response.json()) as { skills?: AgentSkill[] };
          setSkills((body.skills ?? []).filter((s) => s.enabled));
        }
      } catch (err) {
        console.error("Failed to load skills in ChatComposer:", err);
      }
    }
    void loadSkills();
  }, []);

  const focusEnd = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    savedRange.current = range.cloneRange();
  }, [editorRef]);

  const syncFromEditor = useCallback(() => {
    const editor = editorRef.current;
    if (!editor || syncingFromParent.current) return;
    const next = editorPlainText(editor);
    onChangeText(next);

    editor.querySelectorAll<HTMLElement>("[data-skill]").forEach((pill) => {
      let atStart = true;
      for (let n = pill.previousSibling; n; n = n.previousSibling) {
        if (n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() === "") continue;
        atStart = false;
        break;
      }
      pill.toggleAttribute("data-start", atStart);
    });
  }, [editorRef, onChangeText]);

  const saveSelection = () => {
    const editor = editorRef.current;
    const sel = window.getSelection();
    if (sel && sel.rangeCount && editor && editor.contains(sel.anchorNode)) {
      savedRange.current = sel.getRangeAt(0).cloneRange();
    }
  };

  const closeSlash = () => {
    setSlashOpen(false);
    setSlashQuery("");
    setSlashIndex(0);
    setSlashKeyboard(false);
    slashQueryRef.current = "";
    slashTokenRef.current = null;
    ignoreHoverRef.current = false;
  };

  const closeAt = () => {
    setAtOpen(false);
    setAtQuery("");
    setAtIndex(0);
    atTokenRef.current = null;
  };

  const buildSkillPill = (skillId: string, name: string) => {
    const el = document.createElement("span");
    el.className = cx(
      "skill-pill inline-flex max-w-[220px] items-center gap-0.5 rounded-md",
      "bg-indigo-500/10 px-1.5 py-0.5 text-[15px] font-semibold leading-relaxed",
      "text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400",
      "mx-0.5 align-baseline",
    );
    el.setAttribute("contenteditable", "false");
    el.dataset.skill = skillId;
    el.innerHTML =
      `<span class="truncate">/${escapeHtml(skillId)}</span>` +
      `<button type="button" data-remove="1" aria-label="Remove ${escapeHtml(name)}" class="ml-0.5 inline-flex size-3.5 shrink-0 items-center justify-center rounded text-indigo-500/70 hover:text-indigo-600 dark:hover:text-indigo-300">` +
      `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>`;
    return el;
  };

  const insertPillOverRange = (range: Range, skillId: string, name: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    range.deleteContents();
    const pill = buildSkillPill(skillId, name);
    range.insertNode(pill);
    const space = document.createTextNode("\u00A0");
    pill.after(space);
    const after = document.createRange();
    after.setStartAfter(space);
    after.collapse(true);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(after);
    editor.focus();
    savedRange.current = after.cloneRange();
    syncFromEditor();
  };

  const insertPlainOverRange = (range: Range, text: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    range.deleteContents();
    const node = document.createTextNode(text);
    range.insertNode(node);
    const after = document.createRange();
    after.setStartAfter(node);
    after.collapse(true);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(after);
    editor.focus();
    savedRange.current = after.cloneRange();
    syncFromEditor();
  };

  const addSkillFromMenu = (skill: AgentSkill) => {
    const editor = editorRef.current;
    if (!editor) return;
    const sel = window.getSelection();
    let range: Range | null = null;
    if (sel && sel.rangeCount && editor.contains(sel.anchorNode)) {
      range = sel.getRangeAt(0).cloneRange();
    } else if (savedRange.current && editor.contains(savedRange.current.startContainer)) {
      range = savedRange.current.cloneRange();
    }
    if (!range) {
      range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
    }
    insertPillOverRange(range, skill.skill_id, skill.name);
    setMenuOpen(false);
  };

  const applySlash = (skillId: string) => {
    const editor = editorRef.current;
    const skill = skills.find((s) => s.skill_id === skillId);
    if (!editor || !skill) {
      closeSlash();
      return;
    }
    let range: Range | null = null;
    const token = slashTokenRef.current;
    if (
      token &&
      token.node.isConnected &&
      editor.contains(token.node) &&
      token.end <= (token.node.textContent?.length ?? 0)
    ) {
      range = document.createRange();
      range.setStart(token.node, token.start);
      range.setEnd(token.node, token.end);
    } else {
      const sel = window.getSelection();
      if (sel && sel.rangeCount) {
        const caret = sel.getRangeAt(0);
        const node = caret.startContainer;
        if (node.nodeType === Node.TEXT_NODE && editor.contains(node)) {
          const before = (node.textContent ?? "").slice(0, caret.startOffset);
          const m = before.match(/\/([^\s/]*)$/);
          if (m) {
            range = document.createRange();
            range.setStart(node, caret.startOffset - m[0].length);
            range.setEnd(node, caret.startOffset);
          }
        }
      }
    }
    if (!range) {
      closeSlash();
      return;
    }
    insertPillOverRange(range, skill.skill_id, skill.name);
    closeSlash();
  };
  applySlashRef.current = applySlash;

  const applyAt = (tool: ToolPaletteItem) => {
    const editor = editorRef.current;
    if (!editor) {
      closeAt();
      return;
    }
    let range: Range | null = null;
    const token = atTokenRef.current;
    if (
      token &&
      token.node.isConnected &&
      editor.contains(token.node) &&
      token.end <= (token.node.textContent?.length ?? 0)
    ) {
      range = document.createRange();
      range.setStart(token.node, token.start);
      range.setEnd(token.node, token.end);
    } else {
      const sel = window.getSelection();
      if (sel && sel.rangeCount) {
        const caret = sel.getRangeAt(0);
        const node = caret.startContainer;
        if (node.nodeType === Node.TEXT_NODE && editor.contains(node)) {
          const before = (node.textContent ?? "").slice(0, caret.startOffset);
          const m = before.match(/@([^\s@]*)$/);
          if (m) {
            range = document.createRange();
            range.setStart(node, caret.startOffset - m[0].length);
            range.setEnd(node, caret.startOffset);
          }
        }
      }
    }
    if (!range) {
      closeAt();
      return;
    }
    insertPlainOverRange(range, `@[${tool.id}] `);
    closeAt();
  };

  const detectSlashOrAt = () => {
    const editor = editorRef.current;
    const sel = window.getSelection();
    if (!editor || !sel || !sel.rangeCount || !sel.isCollapsed) {
      closeSlash();
      closeAt();
      return;
    }
    const range = sel.getRangeAt(0);
    const node = range.startContainer;
    if (node.nodeType !== Node.TEXT_NODE || !editor.contains(node)) {
      closeSlash();
      closeAt();
      return;
    }
    const before = (node.textContent ?? "").slice(0, range.startOffset);

    const slashMatch = before.match(/(?:^|\s)\/([^\s/]*)$/);
    if (slashMatch) {
      const q = slashMatch[1];
      const slashStart = before.length - slashMatch[1].length - 1;
      slashTokenRef.current = { node: node as Text, start: slashStart, end: range.startOffset };
      if (q !== slashQueryRef.current) {
        slashQueryRef.current = q;
        setSlashIndex(0);
      }
      setSlashQuery(q);
      setSlashOpen(true);
      closeAt();
      return;
    }

    const atMatch = before.match(/(?:^|\s)@([^\s@]*)$/);
    if (atMatch) {
      const q = atMatch[1];
      const atStart = before.length - atMatch[1].length - 1;
      atTokenRef.current = { node: node as Text, start: atStart, end: range.startOffset };
      setAtQuery(q);
      setAtIndex(0);
      setAtOpen(true);
      closeSlash();
      return;
    }

    closeSlash();
    closeAt();
  };

  const onEditorInput = () => {
    syncFromEditor();
    if (enhancePhase === "enhanced") setEnhancePhase("idle");
    detectSlashOrAt();
  };

  const moveSlash = (delta: number) => {
    const results = slashResultsRef.current;
    if (!results.length) return;
    ignoreHoverRef.current = true;
    setSlashKeyboard(true);
    setSlashIndex((i) => (i + delta + results.length * 10) % results.length);
  };

  const handleSlashKey = (e: {
    key: string;
    preventDefault: () => void;
    stopPropagation?: () => void;
  }) => {
    const results = slashResultsRef.current;
    if (!slashOpenRef.current || !results.length) return false;
    if (
      e.key !== "ArrowDown" &&
      e.key !== "ArrowUp" &&
      e.key !== "Enter" &&
      e.key !== "Tab" &&
      e.key !== "Escape"
    ) {
      return false;
    }
    e.preventDefault();
    e.stopPropagation?.();
    if (slashKeyLock.current) return true;
    slashKeyLock.current = true;
    queueMicrotask(() => {
      slashKeyLock.current = false;
    });
    if (e.key === "ArrowDown") {
      moveSlash(1);
      return true;
    }
    if (e.key === "ArrowUp") {
      moveSlash(-1);
      return true;
    }
    if (e.key === "Enter" || e.key === "Tab") {
      applySlashRef.current((results[slashIndexRef.current] ?? results[0]).skill_id);
      return true;
    }
    if (e.key === "Escape") {
      closeSlash();
      return true;
    }
    return false;
  };

  const onEditorKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (handleSlashKey(e)) return;

    if (atOpen && atResults.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAtIndex((i) => (i + 1) % atResults.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setAtIndex((i) => (i - 1 + atResults.length) % atResults.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyAt(atResults[atIndex] ?? atResults[0]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeAt();
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (sendActive && !isBusy) onSubmitText();
    }
  };

  useEffect(() => {
    if (!slashOpen) return;
    const onKey = (e: KeyboardEvent) => {
      handleSlashKey(e);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [slashOpen]);

  useEffect(() => {
    if (!slashOpen || !slashResults.length) return;
    if (slashIndex >= slashResults.length) setSlashIndex(0);
  }, [slashOpen, slashResults.length, slashIndex]);

  // Parent cleared text after send — reset the editor.
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (textInput === "" && editorPlainText(editor) !== "") {
      syncingFromParent.current = true;
      editor.innerHTML = "";
      setEnhancePhase("idle");
      closeSlash();
      closeAt();
      syncingFromParent.current = false;
    }
  }, [textInput, editorRef]);

  const onEditorClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    const remove = (e.target as HTMLElement).closest("[data-remove]");
    if (remove) {
      e.preventDefault();
      const pill = remove.closest<HTMLElement>("[data-skill]");
      if (pill) {
        const sep = pill.nextSibling;
        const w = pill.getBoundingClientRect().width;
        pill.style.maxWidth = `${w}px`;
        pill.style.overflow = "hidden";
        pill.style.whiteSpace = "nowrap";
        void pill.offsetWidth;
        pill.style.transition =
          "max-width 180ms cubic-bezier(0.22,1,0.36,1), margin 180ms cubic-bezier(0.22,1,0.36,1), padding 180ms cubic-bezier(0.22,1,0.36,1), opacity 180ms ease";
        pill.style.maxWidth = "0px";
        pill.style.marginLeft = "0px";
        pill.style.marginRight = "0px";
        pill.style.paddingLeft = "0px";
        pill.style.paddingRight = "0px";
        pill.style.opacity = "0";
        let done = false;
        const finish = () => {
          if (done) return;
          done = true;
          if (sep && sep.nodeType === Node.TEXT_NODE && sep.textContent?.startsWith("\u00A0")) {
            const rest = sep.textContent.slice(1);
            if (rest) sep.textContent = rest;
            else sep.parentNode?.removeChild(sep);
          }
          pill.remove();
          syncFromEditor();
          editorRef.current?.focus();
        };
        setTimeout(finish, 200);
      }
      return;
    }
    saveSelection();
  };

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: PointerEvent) => {
      if (!plusRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      setSkillsExpanded(false);
      return;
    }
    onRefreshTools?.();
  }, [menuOpen, onRefreshTools]);

  // Flip the menu above/below the trigger based on free viewport space, and
  // cap its height to whatever that side actually offers.
  useLayoutEffect(() => {
    if (!menuOpen) return;
    const VIEWPORT_MARGIN = 16;
    const TRIGGER_GAP = 12;
    const MIN_HEIGHT = 220;
    const MAX_HEIGHT = 560;

    const update = () => {
      const trigger = plusRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const spaceAbove = rect.top - VIEWPORT_MARGIN - TRIGGER_GAP;
      const spaceBelow =
        window.innerHeight - rect.bottom - VIEWPORT_MARGIN - TRIGGER_GAP;
      const openUp = spaceAbove >= spaceBelow;
      const available = openUp ? spaceAbove : spaceBelow;
      setMenuPlacement(openUp ? "top" : "bottom");
      setMenuMaxHeight(
        Math.round(Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, available))),
      );
    };

    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [menuOpen]);

  useLayoutEffect(() => {
    if (enhancing || pendingHTML.current === null) return;
    const editor = editorRef.current;
    if (!editor) return;
    syncingFromParent.current = true;
    editor.innerHTML = pendingHTML.current;
    pendingHTML.current = null;
    syncingFromParent.current = false;
    syncFromEditor();
    requestAnimationFrame(focusEnd);

    const frame = frameRef.current;
    const from = flipFrom.current;
    flipFrom.current = null;
    if (!frame || from === null) return;
    const to = frame.offsetHeight;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || from === to) return;
    frame.style.height = from + "px";
    frame.style.overflow = "hidden";
    void frame.offsetHeight;
    frame.style.transition = "height 200ms cubic-bezier(0.22, 1, 0.36, 1)";
    frame.style.height = to + "px";
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      frame.style.transition = "";
      frame.style.height = "";
      frame.style.overflow = "";
      frame.removeEventListener("transitionend", finish);
    };
    frame.addEventListener("transitionend", finish);
    setTimeout(finish, 260);
  }, [enhancePhase, enhancing, editorRef, focusEnd, syncFromEditor]);

  useEffect(() => {
    if (showEnhancePill) {
      setPillMounted(true);
      setPillExiting(false);
      return;
    }
    if (!pillMounted) return;
    if (enhancing) {
      setPillMounted(false);
      setPillExiting(false);
      return;
    }
    setPillExiting(true);
    const t = setTimeout(() => {
      setPillMounted(false);
      setPillExiting(false);
    }, 200);
    return () => clearTimeout(t);
  }, [showEnhancePill, enhancing, pillMounted]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const runEnhance = async () => {
    if (!hasText || enhancing) return;
    preEnhanceHTML.current = editorRef.current?.innerHTML ?? "";
    setEnhancePhase("enhancing");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const result = await onEnhance(textInput, ac.signal);
      if (ac.signal.aborted) return;
      pendingHTML.current = escapeHtml(result);
      flipFrom.current = frameRef.current?.offsetHeight ?? null;
      setEnhancePhase("enhanced");
    } catch {
      if (ac.signal.aborted) return;
      pendingHTML.current = preEnhanceHTML.current;
      setEnhancePhase("idle");
    }
  };

  const revert = () => {
    abortRef.current?.abort();
    pendingHTML.current = preEnhanceHTML.current;
    flipFrom.current = frameRef.current?.offsetHeight ?? null;
    setEnhancePhase("idle");
  };

  const menuSurface =
    "border border-zinc-200/80 dark:border-white/8 bg-white/90 dark:bg-[#1c1c1e]/90 backdrop-blur-md shadow-2xl rounded-2xl";

  const menuItemClass = cx(
    "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-[13px] transition-colors",
    "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/[0.06]",
    "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
  );

  return (
    <div
      ref={frameRef}
      className={cx(
        "relative flex flex-col transition-all",
        isLanding
          ? "min-h-[120px] rounded-[24px] border border-white/55 bg-white/70 p-1 shadow-[0_18px_50px_rgba(0,0,0,0.18)] backdrop-blur-xl focus-within:border-sky-400/70 dark:border-white/25 dark:bg-black/30"
          : "min-h-[80px] rounded-[24px] border border-zinc-200/80 bg-transparent p-1 focus-within:border-indigo-500/30 dark:border-white/8",
        enhancing && "opacity-90",
      )}
    >
      {/* Slash skills palette */}
      {slashOpen && !enhancing && (
        <div className="absolute bottom-full left-0 right-0 z-50 mb-3 px-4">
          <div className={cx(menuSurface, "max-h-60 overflow-y-auto p-1 no-scrollbar")}>
            <div className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-zinc-500">
              Skills
            </div>
            {slashResults.length ? (
              <div
                className="flex flex-col gap-1"
                role="listbox"
                aria-label="Skills"
                data-keyboard={slashKeyboard || undefined}
                onMouseMove={() => {
                  ignoreHoverRef.current = false;
                  if (slashKeyboard) setSlashKeyboard(false);
                }}
              >
                {slashResults.map((skill, i) => (
                  <button
                    key={skill.skill_id}
                    type="button"
                    role="option"
                    aria-selected={i === slashIndex}
                    className={cx(
                      "flex w-full cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-left transition-colors",
                      i === slashIndex
                        ? "bg-indigo-500/10 font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400"
                        : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/[0.04]",
                    )}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => {
                      if (ignoreHoverRef.current) return;
                      setSlashIndex(i);
                    }}
                    onClick={() => applySlash(skill.skill_id)}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="text-sm font-semibold">/{skill.skill_id}</span>
                      <span className="truncate text-xs text-zinc-500">({skill.name})</span>
                    </span>
                    <span className="max-w-[250px] truncate text-xs text-zinc-400">
                      {skill.description}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-2 text-sm text-zinc-500">No matching skills</div>
            )}
          </div>
        </div>
      )}

      {/* @ tools palette */}
      {atOpen && !enhancing && atResults.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 z-50 mb-3 px-4">
          <div className={cx(menuSurface, "max-h-60 overflow-y-auto p-1 no-scrollbar")}>
            <div className="flex flex-col gap-1" role="listbox" aria-label="Tools">
              {atResults.map((tool, i) => (
                <button
                  key={tool.id}
                  type="button"
                  role="option"
                  aria-selected={i === atIndex}
                  className={cx(
                    "flex w-full cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-left transition-colors",
                    i === atIndex
                      ? "bg-emerald-500/10 font-medium text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400"
                      : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/[0.04]",
                  )}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setAtIndex(i)}
                  onClick={() => applyAt(tool)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="text-sm font-semibold">@{tool.id}</span>
                    <span className="text-xs text-zinc-400">({tool.category})</span>
                  </span>
                  <span className="max-w-[250px] truncate text-xs text-zinc-400">
                    {tool.description}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Attachments */}
      {uploadedFiles.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-2 px-3 pt-2">
          {uploadedFiles.map((file) => (
            <span
              key={file.path}
              className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-200"
            >
              <Paperclip className="h-3.5 w-3.5" />
              <span className="max-w-44 truncate">{file.name}</span>
              <button
                type="button"
                onClick={() => onRemoveFile(file.path)}
                className="text-zinc-400 transition-colors hover:text-zinc-200"
                aria-label={`Remove ${file.name}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Editor */}
      <div
        className={cx(
          "relative flex w-full items-start px-4",
          isLanding ? "min-h-[80px] py-3" : "min-h-[80px] py-4",
        )}
      >
        {enhancing ? (
          <div
            className="w-full whitespace-pre-wrap break-words text-[18px] leading-relaxed text-zinc-500"
            aria-live="polite"
          >
            {textInput}
          </div>
        ) : (
          <div
            ref={editorRef}
            className={cx(
              "relative z-10 w-full max-h-60 overflow-y-auto break-words bg-transparent text-[18px] leading-relaxed",
              "text-zinc-900 outline-none no-scrollbar dark:text-zinc-200",
              !hasText && "min-h-[1.5em]",
            )}
            contentEditable
            suppressContentEditableWarning
            role="textbox"
            aria-multiline="true"
            aria-label="Send message to CoComputer"
            data-placeholder="Send message to CoComputer"
            data-empty={!hasText || undefined}
            onInput={onEditorInput}
            onKeyDown={onEditorKeyDown}
            onKeyUp={saveSelection}
            onMouseUp={saveSelection}
            onBlur={saveSelection}
            onClick={onEditorClick}
          />
        )}
        {!hasText && !enhancing && (
          <div
            aria-hidden
            className={cx(
              "pointer-events-none absolute inset-x-4 text-[18px] font-medium leading-relaxed text-zinc-500",
              isLanding ? "top-3" : "top-4",
            )}
          >
            Send message to CoComputer
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div className="mt-1 flex items-center justify-between px-2 pb-2">
        <div className="flex items-center gap-2">
          <div className="relative" ref={plusRef}>
            <button
              type="button"
              className={cx(
                "relative flex items-center justify-center rounded-full border border-zinc-700/50 p-1.5 transition-colors",
                "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200",
                "disabled:opacity-40",
                menuOpen && "bg-zinc-800 text-zinc-200",
              )}
              style={{
                backgroundColor: menuOpen
                  ? undefined
                  : "var(--color-ai-chat-composer-add-background)",
              }}
              aria-label="Add attachment, skill, or tools"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              <Plus className="h-4 w-4" />
              {selectionCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-500 text-[10px] font-bold text-white">
                  {selectionCount}
                </span>
              )}
            </button>

            {menuOpen && (
              <div
                className={cx(
                  menuSurface,
                  "absolute left-0 z-50 flex w-80 flex-col overflow-hidden p-1.5",
                  menuPlacement === "top"
                    ? "bottom-full mb-3 origin-bottom-left"
                    : "top-full mt-3 origin-top-left",
                  "animate-in fade-in-0 zoom-in-95 duration-150",
                )}
                style={{ maxHeight: menuMaxHeight }}
              >
                <div className="shrink-0 space-y-0.5">
                  <button
                    type="button"
                    className={menuItemClass}
                    disabled={uploadDisabled}
                    onClick={() => {
                      if (uploadDisabled) return;
                      onOpenFilePicker("image");
                      setMenuOpen(false);
                    }}
                  >
                    <ImageIcon className="h-4 w-4 shrink-0 text-zinc-500" />
                    <span className="flex-1 text-left">Add photos</span>
                  </button>
                  <button
                    type="button"
                    className={menuItemClass}
                    disabled={uploadDisabled}
                    onClick={() => {
                      if (uploadDisabled) return;
                      onOpenFilePicker("file");
                      setMenuOpen(false);
                    }}
                  >
                    <Paperclip className="h-4 w-4 shrink-0 text-zinc-500" />
                    <span className="flex-1 text-left">Attach files</span>
                  </button>
                </div>

                <div className="my-1.5 h-px shrink-0 bg-zinc-200/80 dark:bg-white/5" />

                <div className="flex min-h-0 shrink-0 flex-col">
                  <button
                    type="button"
                    className={menuItemClass}
                    aria-expanded={skillsExpanded}
                    onClick={() => setSkillsExpanded((o) => !o)}
                  >
                    <BookOpen className="h-4 w-4 shrink-0 text-zinc-500" />
                    <span className="flex-1 text-left">Skills</span>
                    {skills.length > 0 && (
                      <span className="text-[11px] tabular-nums text-zinc-400 dark:text-zinc-600">
                        {skills.length}
                      </span>
                    )}
                    <ChevronDown
                      className={cx(
                        "h-4 w-4 shrink-0 text-zinc-500 transition-transform duration-200",
                        skillsExpanded && "rotate-180",
                      )}
                    />
                  </button>
                  {skillsExpanded && (
                    <div className="custom-scrollbar mt-0.5 max-h-44 space-y-0.5 overflow-y-auto pl-2">
                      {skills.length ? (
                        skills.map((sk) => (
                          <button
                            key={sk.skill_id}
                            type="button"
                            className="flex w-full flex-col rounded-lg px-3 py-1.5 text-left transition-colors hover:bg-zinc-100 dark:hover:bg-white/[0.06]"
                            onClick={() => addSkillFromMenu(sk)}
                          >
                            <span className="text-[13px] font-medium text-zinc-800 dark:text-zinc-200">
                              /{sk.skill_id}
                            </span>
                            <span className="truncate text-[11px] text-zinc-500">
                              {sk.name}
                            </span>
                          </button>
                        ))
                      ) : (
                        <div className="px-3 py-2 text-[13px] text-zinc-500">
                          No skills enabled
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="my-1.5 h-px shrink-0 bg-zinc-200/80 dark:bg-white/5" />

                <ToolPickerPanel
                  availableConnectors={availableConnectors}
                  selectedConnectorIds={selectedConnectorIds}
                  onToggleConnector={onToggleConnector}
                  onToggleAllConnectors={onToggleAllConnectors}
                  selectedToolIds={selectedToolIds}
                  onToggleTool={onToggleTool}
                  onToggleAllTools={onToggleAllTools}
                  loading={connectorsLoading}
                />
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onShowDesktop}
            className="rounded p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
            title="Workspace Context"
          >
            <Monitor className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          {enhancing ? (
            <span
              className="flex items-center justify-center rounded-full border border-zinc-700/50 p-1.5 text-zinc-400"
              aria-label="Enhancing prompt"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
            </span>
          ) : (
            pillMounted && (
              <button
                type="button"
                className={cx(
                  "rounded-full border border-zinc-700/50 px-3 py-1 text-xs font-medium transition-all",
                  "text-zinc-300 hover:bg-zinc-800 hover:text-white",
                  pillExiting && "scale-95 opacity-0",
                )}
                onClick={enhancePhase === "enhanced" ? revert : runEnhance}
              >
                {enhancePhase === "enhanced" ? "Revert" : "Enhance Prompt"}
              </button>
            )
          )}

          <button
            type="button"
            onClick={onToggleMic}
            disabled={voiceStatus !== "connected"}
            className={cx(
              "rounded p-1.5 transition-colors disabled:opacity-40",
              isRecording
                ? "bg-red-500/10 text-red-400"
                : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200",
            )}
            title="Voice Input"
          >
            <Mic className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={isBusy ? onStopAgent : onSubmitText}
            disabled={!isBusy && !sendActive}
            className={cx(
              "rounded-full border p-1.5 transition-colors",
              isBusy
                ? "border-red-500/30 bg-red-500/10 text-red-500 hover:bg-red-500/20"
                : sendActive
                  ? "border-zinc-700/50 bg-[#3a3a3c] text-indigo-400 hover:bg-indigo-500 hover:text-white"
                  : "cursor-not-allowed border-zinc-700/50 bg-zinc-800 text-zinc-500 opacity-50",
            )}
            title={isBusy ? "Stop" : "Send"}
            aria-label={isBusy ? "Stop" : "Send"}
          >
            {isBusy ? (
              <Square className="h-4 w-4 fill-current" />
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
