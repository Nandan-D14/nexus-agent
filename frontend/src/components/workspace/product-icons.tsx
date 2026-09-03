/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import React from "react";

type IconProps = {
  className?: string;
  size?: number;
};

export function GoogleCalendarLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <path
        d="M19.5 4.5h-15A2.25 2.25 0 002.25 6.75v12.5A2.25 2.25 0 004.5 21.5h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5z"
        fill="#ffffff"
      />
      <path
        d="M19.5 4.5h-15A2.25 2.25 0 002.25 6.75v2.25h19.5V6.75A2.25 2.25 0 0019.5 4.5z"
        fill="#1A73E8"
      />
      <path
        d="M7.5 2.5v4M16.5 2.5v4"
        stroke="#1A73E8"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <text
        x="12"
        y="17"
        textAnchor="middle"
        fontSize="8"
        fontFamily="sans-serif"
        fontWeight="bold"
        fill="#1A73E8"
      >
        31
      </text>
    </svg>
  );
}

export function GmailLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <path
        d="M20 5.5H4a2 2 0 00-2 2v9a2 2 0 002 2h16a2 2 0 002-2v-9a2 2 0 00-2-2z"
        fill="#F2F2F2"
      />
      <path
        d="M2 7.5l10 6.5 10-6.5V7.5L12 14 2 7.5z"
        fill="#EA4335"
      />
      <path
        d="M2 7.5v9a2 2 0 002 2h3V9.5L2 7.5z"
        fill="#4285F4"
      />
      <path
        d="M22 7.5v9a2 2 0 01-2 2h-3V9.5l5-2z"
        fill="#34A853"
      />
      <path
        d="M7 18.5h10v-9L12 13 7 9.5v9z"
        fill="#FBBC05"
      />
      <path
        d="M2 7.5l5 3.5 5-3.5-10-2z"
        fill="#C5221F"
      />
      <path
        d="M22 7.5l-5 3.5-5-3.5 10-2z"
        fill="#EA4335"
      />
    </svg>
  );
}

export function SlackLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <path
        d="M5.5 10.5a2 2 0 100-4 2 2 0 000 4z"
        fill="#E01E5A"
      />
      <path
        d="M6.5 10.5H2a2 2 0 000 4h4.5v-4z"
        fill="#E01E5A"
      />
      <path
        d="M13.5 5.5a2 2 0 10-4 0 2 2 0 004 0z"
        fill="#36C5F0"
      />
      <path
        d="M13.5 6.5V2a2 2 0 00-4 0v4.5h4z"
        fill="#36C5F0"
      />
      <path
        d="M18.5 13.5a2 2 0 100 4 2 2 0 000-4z"
        fill="#2EB67D"
      />
      <path
        d="M17.5 13.5H22a2 2 0 000-4h-4.5v4z"
        fill="#2EB67D"
      />
      <path
        d="M10.5 18.5a2 2 0 104 0 2 2 0 00-4 0z"
        fill="#ECB22E"
      />
      <path
        d="M10.5 17.5V22a2 2 0 004 0v-4.5h-4z"
        fill="#ECB22E"
      />
    </svg>
  );
}

export function StripeLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <rect width="24" height="24" rx="6" fill="#635BFF" />
      <path
        d="M11.6 9.8c0-.7.6-1 1.6-1 1.4 0 3.2.4 4.5 1.1V6.2c-1.4-.6-3-.9-4.5-.9-3.8 0-6.3 2-6.3 5.3 0 5.2 7.1 4.3 7.1 6.6 0 .8-.7 1.1-1.7 1.1-1.6 0-3.7-.6-5.2-1.5v3.8c1.7.7 3.5 1 5.2 1 3.9 0 6.6-1.9 6.6-5.4-.1-5.6-7.3-4.6-7.3-6.4z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function LinearLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <rect width="24" height="24" rx="6" fill="#5E6AD2" />
      <path
        d="M4.8 14.7L14.7 4.8C13.2 3.6 11.2 3 9 3 4.6 3 1 6.6 1 11c0 2.2.6 4.2 1.8 5.7l2-2z"
        fill="#FFFFFF"
      />
      <path
        d="M19.2 9.3L9.3 19.2C10.8 20.4 12.8 21 15 21c4.4 0 8-3.6 8-8 0-2.2-.6-4.2-1.8-5.7l-2 2z"
        fill="#FFFFFF"
      />
      <path
        d="M6.3 17.7l11.4-11.4c-.6-.7-1.3-1.3-2-1.8L4.3 15.9c.5.7 1.2 1.3 2 1.8z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export function InsightsLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <defs>
        <linearGradient id="insightsGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818CF8" />
          <stop offset="100%" stopColor="#C084FC" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill="url(#insightsGrad)" />
      <rect x="5" y="13" width="3" height="7" rx="1" fill="#FFFFFF" />
      <rect x="10.5" y="8" width="3" height="12" rx="1" fill="#FFFFFF" />
      <rect x="16" y="4" width="3" height="16" rx="1" fill="#FFFFFF" />
    </svg>
  );
}

export function GitHubLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

export function GoogleDriveLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <path d="M8.2 4L1.2 16.2h7l7-12.2H8.2z" fill="#0066DA" />
      <path d="M15.2 4l7 12.2-3.5 6.1-7-12.2L15.2 4z" fill="#00AC47" />
      <path d="M1.2 16.2L4.7 22.3h14l-3.5-6.1H1.2z" fill="#EA4335" />
      <path d="M8.2 4h7.6l7 12.2h-7.6L8.2 4z" fill="#FFBA00" />
    </svg>
  );
}

export function NotionLogo({ className = "size-8", size }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      width={size}
      height={size}
      fill="none"
    >
      <rect width="24" height="24" rx="6" fill="#000000" />
      <path
        d="M4.5 4.5v15h15v-15h-15zm3 2.5h2.2l4.8 7.3V7h2v10h-2.2L9.5 9.7V17h-2V7z"
        fill="#FFFFFF"
      />
    </svg>
  );
}
