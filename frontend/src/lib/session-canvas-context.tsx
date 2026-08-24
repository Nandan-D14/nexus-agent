/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type MutableRefObject,
  type ReactNode,
} from "react";

import type { TodoItem } from "@/components/todo-list";
import type { RunArtifact } from "@/lib/message-types";
import {
  documentFromArtifact,
  documentFromWorkspaceFile,
  upsertCanvasDocument,
  type SessionCanvasDocument,
  type SessionCanvasOpenReason,
} from "@/lib/session-canvas";

export type SessionCanvasApi = {
  openDocument: (
    doc: SessionCanvasDocument,
    reason?: SessionCanvasOpenReason,
  ) => void;
  openFromArtifact: (
    artifact: RunArtifact,
    reason?: SessionCanvasOpenReason,
  ) => SessionCanvasDocument;
  openFromWorkspaceFile: (
    path: string,
    content: string,
    reason?: SessionCanvasOpenReason,
  ) => SessionCanvasDocument;
  selectDocument: (id: string) => void;
};

type SessionCanvasContextValue = SessionCanvasApi & {
  documents: SessionCanvasDocument[];
  activeId: string | null;
  todoItems: TodoItem[];
};

const SessionCanvasContext = createContext<SessionCanvasContextValue | null>(
  null,
);

type ProviderProps = {
  children: ReactNode;
  todoItems: TodoItem[];
  onRequestPane: (reason: SessionCanvasOpenReason) => void;
  apiRef?: MutableRefObject<SessionCanvasApi | null>;
};

export function SessionCanvasProvider({
  children,
  todoItems,
  onRequestPane,
  apiRef,
}: ProviderProps) {
  const [documents, setDocuments] = useState<SessionCanvasDocument[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const openDocument = useCallback(
    (doc: SessionCanvasDocument, reason: SessionCanvasOpenReason = "user") => {
      setDocuments((prev) => upsertCanvasDocument(prev, doc));
      setActiveId(doc.id);
      onRequestPane(reason);
    },
    [onRequestPane],
  );

  const openFromArtifact = useCallback(
    (artifact: RunArtifact, reason: SessionCanvasOpenReason = "user") => {
      const doc = documentFromArtifact(artifact);
      openDocument(doc, reason);
      return doc;
    },
    [openDocument],
  );

  const openFromWorkspaceFile = useCallback(
    (path: string, content: string, reason: SessionCanvasOpenReason = "user") => {
      const doc = documentFromWorkspaceFile(path, content);
      openDocument(doc, reason);
      return doc;
    },
    [openDocument],
  );

  const selectDocument = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const api = useMemo<SessionCanvasApi>(
    () => ({
      openDocument,
      openFromArtifact,
      openFromWorkspaceFile,
      selectDocument,
    }),
    [openDocument, openFromArtifact, openFromWorkspaceFile, selectDocument],
  );

  if (apiRef) {
    apiRef.current = api;
  }

  const value = useMemo<SessionCanvasContextValue>(
    () => ({
      ...api,
      documents,
      activeId,
      todoItems,
    }),
    [activeId, api, documents, todoItems],
  );

  return (
    <SessionCanvasContext.Provider value={value}>
      {children}
    </SessionCanvasContext.Provider>
  );
}

export function useSessionCanvas(): SessionCanvasContextValue | null {
  return useContext(SessionCanvasContext);
}
