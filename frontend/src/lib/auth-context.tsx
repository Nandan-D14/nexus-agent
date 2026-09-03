/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  GoogleAuthProvider,
  getRedirectResult,
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  type User,
} from "firebase/auth";
import {
  doc,
  getDoc,
  serverTimestamp,
  setDoc,
} from "firebase/firestore";
import type { QueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { clearAuthTokenCache } from "@/lib/api-client";
import { auth, db, isRecoverableFirestoreError } from "@/lib/firebase-client";

export type AppUser = {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
};

type AuthContextValue = {
  user: AppUser | null;
  isLoading: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOutUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const googleProvider = new GoogleAuthProvider();

function mapUser(user: User): AppUser {
  return {
    uid: user.uid,
    email: user.email,
    displayName: user.displayName,
    photoURL: user.photoURL,
  };
}

async function syncUserProfile(user: User) {
  const ref = doc(db, "users", user.uid);
  const snapshot = await getDoc(ref);
  const payload = {
    uid: user.uid,
    email: user.email,
    displayName: user.displayName,
    photoURL: user.photoURL,
    lastLoginAt: serverTimestamp(),
    ...(snapshot.exists() ? {} : { createdAt: serverTimestamp() }),
  };
  await setDoc(ref, payload, { merge: true });
}

export function AuthProvider({
  children,
  queryClient,
}: {
  children: ReactNode;
  queryClient: QueryClient;
}) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Capture the redirect result when the user returns from the Google sign-in page.
    getRedirectResult(auth).catch((err) => {
      // Ignore benign redirect errors (e.g. no redirect pending or user cancelled).
      const code = (err as { code?: string })?.code;
      if (
        code &&
        code !== "auth/credential-already-in-use" &&
        code !== "auth/null-user"
      ) {
        console.error("[AuthProvider] Redirect result error", err);
      }
    });

    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      if (firebaseUser) {
        setUser(mapUser(firebaseUser));
        void syncUserProfile(firebaseUser).catch((err) => {
          if (isRecoverableFirestoreError(err)) {
            return;
          }
          console.error("[AuthProvider] Failed to sync user profile", err);
        });
      } else {
        setUser(null);
        clearAuthTokenCache();
        queryClient.clear();
      }
      setIsLoading(false);
    });

    return unsubscribe;
  }, [queryClient]);

  const signInWithGoogle = useCallback(async () => {
    setError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err: unknown) {
      const authErr = err as { code?: string; message?: string };
      if (
        authErr?.code === "auth/popup-blocked" ||
        authErr?.code === "auth/cancelled-popup-request"
      ) {
        try {
          await signInWithRedirect(auth, googleProvider);
          return;
        } catch (redirectErr) {
          setError(
            redirectErr instanceof Error
              ? redirectErr.message
              : "Google sign-in failed",
          );
          throw redirectErr;
        }
      }
      if (authErr?.code === "auth/popup-closed-by-user") {
        return;
      }
      setError(err instanceof Error ? err.message : "Google sign-in failed");
      throw err;
    }
  }, []);

  const signOutUser = useCallback(async () => {
    try {
      await signOut(auth);
      clearAuthTokenCache();
      queryClient.clear();
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sign-out failed";
      console.error("[signOutUser]", err);
      setError(message);
    }
  }, [queryClient, setError]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      error,
      signInWithGoogle,
      signOutUser,
    }),
    [error, isLoading, signInWithGoogle, signOutUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
