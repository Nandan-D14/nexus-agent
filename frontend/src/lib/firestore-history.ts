"use client";

import {
  collection,
  getDocs,
  limit,
  orderBy,
  query,
  where,
} from "firebase/firestore";

import { db } from "@/lib/firebase-client";
import type { ArchivedMessage, RecentSession } from "@/lib/message-types";

export async function listRecentSessions(
  ownerId: string,
  count = 8,
): Promise<RecentSession[]> {
  const sessionsQuery = query(
    collection(db, "sessions"),
    where("ownerId", "==", ownerId),
    orderBy("updatedAt", "desc"),
    limit(count),
  );

  const snapshot = await getDocs(sessionsQuery);
  return snapshot.docs.map((docSnapshot) => {
    const data = docSnapshot.data();
    return {
      session_id: docSnapshot.id,
      title: typeof data.title === "string" ? data.title : "Untitled session",
      status: typeof data.status === "string" ? data.status : "ended",
      summary: typeof data.summary === "string" ? data.summary : null,
      created_at: data.createdAt?.toDate?.().toISOString?.() || null,
      updated_at: data.updatedAt?.toDate?.().toISOString?.() || null,
      message_count:
        typeof data.messageCount === "number" ? data.messageCount : 0,
    };
  });
}

export async function listArchivedMessages(
  sessionId: string,
): Promise<ArchivedMessage[]> {
  if (!sessionId || typeof sessionId !== "string") {
    throw new Error(
      "listArchivedMessages: sessionId must be a non-empty string",
    );
  }
  if (!/^[\w-]+$/.test(sessionId)) {
    throw new Error(
      `listArchivedMessages: sessionId contains invalid characters – only alphanumeric, hyphen, and underscore are allowed (got "${sessionId}")`,
    );
  }

  const messagesQuery = query(
    collection(db, "sessions", sessionId, "messages"),
    orderBy("turnIndex", "asc"),
  );

  const snapshot = await getDocs(messagesQuery);
  return snapshot.docs.map((docSnapshot) => {
    const data = docSnapshot.data();
    return {
      id: docSnapshot.id,
      role: data.role === "user" ? "user" : "agent",
      text: typeof data.text === "string" ? data.text : "",
      source: typeof data.source === "string" ? data.source : undefined,
      turn_index: typeof data.turnIndex === "number" ? data.turnIndex : 0,
      created_at: data.createdAt?.toDate?.().toISOString?.() || null,
    };
  });
}
