"use client";

import { useEffect, useRef, useState, type ComponentProps } from "react";
import { RiLogoutCircleLine, RiMailLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { useAuth } from "@/lib/auth-context";
import {
  disconnectGoogleDrive,
  fetchGoogleDriveAuthUrl,
  fetchUserSettings,
  patchAppSettings,
  readAppSettings,
  splitDisplayName,
} from "@/lib/user-settings";
import { cx } from "@/utils/cx";
import { SettingsCard, SettingsRow, SettingsValueField } from "./settings-rows";

function SavableInput({
  initialValue,
  onCommit,
  ...inputProps
}: { initialValue: string; onCommit?: (value: string) => void | Promise<void> } & Omit<
  ComponentProps<typeof Input>,
  "value" | "onChange" | "defaultValue"
>) {
  const [value, setValue] = useState(initialValue);
  const committed = useRef(initialValue);

  useEffect(() => {
    setValue(initialValue);
    committed.current = initialValue;
  }, [initialValue]);

  return (
    <Input
      size="small"
      {...inputProps}
      value={value}
      onChange={setValue}
      onKeyDown={(event) => {
        if (event.key === "Enter") (event.target as HTMLElement).blur();
      }}
      onBlur={() => {
        if (value === committed.current) return;
        committed.current = value;
        void onCommit?.(value);
      }}
      className={cx("w-[202px] shrink-0", inputProps.className)}
    />
  );
}

export function SettingsProfile({ onSaved }: { onSaved?: () => void } = {}) {
  const { user, signOutUser } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [driveConnected, setDriveConnected] = useState(false);
  const [driveBusy, setDriveBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchUserSettings()
      .then((data) => {
        if (cancelled) return;
        const parsed = readAppSettings(data);
        const fallback = splitDisplayName(user?.displayName);
        setFirstName(parsed.profile.firstName || fallback.firstName);
        setLastName(parsed.profile.lastName || fallback.lastName);
        setDriveConnected(data.googleDriveConnected);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load profile.");
        const fallback = splitDisplayName(user?.displayName);
        setFirstName(fallback.firstName);
        setLastName(fallback.lastName);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.displayName]);

  const saveName = async (nextFirst: string, nextLast: string) => {
    setError(null);
    try {
      await patchAppSettings({ profile: { firstName: nextFirst, lastName: nextLast } });
      onSaved?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save profile.");
    }
  };

  const handleDrive = async () => {
    setDriveBusy(true);
    setError(null);
    try {
      if (driveConnected) {
        await disconnectGoogleDrive();
        setDriveConnected(false);
        onSaved?.();
      } else {
        const url = await fetchGoogleDriveAuthUrl();
        window.location.href = url;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update Google Drive.");
    } finally {
      setDriveBusy(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      {error ? (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {error}
        </div>
      ) : null}

      <SettingsCard>
        <SettingsRow label="Email">
          <SettingsValueField icon={RiMailLine} muted>
            {user?.email || "Not signed in"}
          </SettingsValueField>
        </SettingsRow>
        <SettingsRow label="First name">
          <SavableInput
            aria-label="First name"
            initialValue={firstName}
            isDisabled={loading}
            onCommit={(value) => {
              setFirstName(value);
              void saveName(value, lastName);
            }}
          />
        </SettingsRow>
        <SettingsRow label="Last name">
          <SavableInput
            aria-label="Last name"
            initialValue={lastName}
            isDisabled={loading}
            onCommit={(value) => {
              setLastName(value);
              void saveName(firstName, value);
            }}
          />
        </SettingsRow>
      </SettingsCard>

      <SettingsCard>
        <SettingsRow
          label="Google Drive"
          description={
            driveConnected
              ? "Connected — the agent can read and write Drive files"
              : "Connect Drive to let the agent use your files"
          }
        >
          <Button
            variant="secondary"
            size="small"
            disabled={driveBusy}
            onClick={() => void handleDrive()}
          >
            {driveBusy ? "Working…" : driveConnected ? "Disconnect" : "Connect"}
          </Button>
        </SettingsRow>
        <SettingsRow label="Account ID">
          <SettingsValueField muted>{user?.uid || "—"}</SettingsValueField>
        </SettingsRow>
        <SettingsRow label="Log out">
          <Button
            variant="secondary"
            size="small"
            leadingIcon={RiLogoutCircleLine}
            onClick={() => void signOutUser()}
          >
            Logout
          </Button>
        </SettingsRow>
      </SettingsCard>
    </div>
  );
}
