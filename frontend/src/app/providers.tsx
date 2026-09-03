"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { ToastProvider } from "@/components/toast-provider";
import { isQuotaExceededError } from "@/lib/api-client";
import { AuthProvider } from "@/lib/auth-context";
import { SignInGateProvider } from "@/components/auth/sign-in-gate";
import { SettingsProvider } from "@/lib/settings-context";
import { LandingChromeProvider } from "@/lib/landing-chrome-context";
import { LiveDesktopProvider } from "@/components/live-desktop-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              if (isQuotaExceededError(error)) return false;
              return failureCount < 1;
            },
            refetchOnWindowFocus: (query) => !isQuotaExceededError(query.state.error),
            refetchOnReconnect: (query) => !isQuotaExceededError(query.state.error),
          },
        },
      }),
  );

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <ToastProvider>
        <AuthProvider queryClient={queryClient}>
          <QueryClientProvider client={queryClient}>
            <SettingsProvider>
              <LandingChromeProvider>
                <SignInGateProvider>
                  <LiveDesktopProvider>{children}</LiveDesktopProvider>
                </SignInGateProvider>
              </LandingChromeProvider>
            </SettingsProvider>
          </QueryClientProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
