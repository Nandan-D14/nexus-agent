"""Manual beta access operations for a small trusted rollout."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.beta_access import (  # noqa: E402
    append_beta_application_to_sheet,
    build_sheet_sync_state,
    generate_beta_access_code,
    hash_beta_access_code,
    normalize_beta_profile,
    resolve_beta_admin_emails,
)
from nexus.history_repository import FirestoreHistoryRepository  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Nexus beta access.")
    parser.add_argument("--uid", help="Firebase user id")
    parser.add_argument("--email", help="User email address")
    parser.add_argument("--admin-email", help="Admin email recorded on approvals and revocations")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show beta application and access state")

    approve = subparsers.add_parser("approve", help="Approve the user and issue a beta access code")
    approve.add_argument("--print-only", action="store_true", help="Only print the code after storing it")

    reject = subparsers.add_parser("reject", help="Reject the beta application")
    reject.add_argument("--reason", default="", help="Optional reason saved in Firestore")

    revoke = subparsers.add_parser("revoke", help="Revoke beta access and all issued codes")
    revoke.add_argument("--reason", default="", help="Optional revoke reason saved in Firestore")

    subparsers.add_parser("resync-sheet", help="Retry Google Sheets sync for the stored application")
    return parser


async def _resolve_user(repo: FirestoreHistoryRepository, uid: str | None, email: str | None) -> tuple[str, dict]:
    if uid:
        user_settings = await repo.get_user_settings(uid)
        if user_settings:
            return uid, user_settings
        raise SystemExit(f"No user document found for uid={uid}")
    if email:
        user_record = await repo.find_user_by_email(email)
        if user_record:
            uid = str(user_record.get("uid", ""))
            if uid:
                return uid, user_record
        raise SystemExit(f"No user document found for email={email}")
    raise SystemExit("Provide either --uid or --email.")


def _resolve_admin_email(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    admins = sorted(resolve_beta_admin_emails())
    if admins:
        return admins[0]
    raise SystemExit("Provide --admin-email or configure BETA_ADMIN_EMAILS.")


async def _print_status(repo: FirestoreHistoryRepository, uid: str, user_record: dict) -> None:
    application = await repo.get_beta_application(uid)
    profile = normalize_beta_profile(user_record)
    print(f"uid: {uid}")
    print(f"email: {user_record.get('email', '')}")
    print(f"status: {profile.get('status')}")
    print(f"access_code_redeemed: {profile.get('accessCodeRedeemed')}")
    print(f"approved_at: {profile.get('approvedAt')}")
    print(f"redeemed_at: {profile.get('redeemedAt')}")
    if application:
        print(f"application_updated_at: {application.get('updatedAt')}")
        sheet_sync = application.get("sheetSync", {}) if isinstance(application.get("sheetSync"), dict) else {}
        print(f"sheet_sync_status: {sheet_sync.get('status')}")
        if sheet_sync.get("lastError"):
            print(f"sheet_sync_error: {sheet_sync.get('lastError')}")


async def _approve(repo: FirestoreHistoryRepository, uid: str, admin_email: str) -> None:
    code = generate_beta_access_code()
    await repo.issue_beta_access_code(
        uid=uid,
        admin_email=admin_email,
        code_hash=hash_beta_access_code(code),
        code_preview=code.split("-")[-1],
    )
    print(f"Approved uid={uid}")
    print(f"Beta access code: {code}")


async def _reject(repo: FirestoreHistoryRepository, uid: str, admin_email: str, reason: str) -> None:
    await repo.reject_beta_application(uid=uid, admin_email=admin_email, reason=reason or None)
    print(f"Rejected uid={uid}")


async def _revoke(repo: FirestoreHistoryRepository, uid: str, admin_email: str, reason: str) -> None:
    await repo.revoke_beta_access(uid=uid, admin_email=admin_email, reason=reason or None)
    print(f"Revoked uid={uid}")


async def _resync_sheet(repo: FirestoreHistoryRepository, uid: str) -> None:
    application = await repo.get_beta_application(uid)
    if not application:
        raise SystemExit(f"No beta application found for uid={uid}")
    try:
        append_beta_application_to_sheet(application)
    except Exception as exc:
        await repo.upsert_beta_application(
            uid,
            {
                "sheetSyncStatus": "error",
                "sheetSync": build_sheet_sync_state("error", str(exc)),
            },
        )
        raise SystemExit(f"Sheets resync failed: {exc}") from exc
    await repo.upsert_beta_application(
        uid,
        {
            "sheetSyncStatus": "synced",
            "sheetSync": build_sheet_sync_state("synced"),
        },
    )
    print(f"Resynced application for uid={uid}")


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    repo = FirestoreHistoryRepository()
    uid, user_record = await _resolve_user(repo, args.uid, args.email)

    if args.command == "status":
        await _print_status(repo, uid, user_record)
        return

    if args.command == "approve":
        await _approve(repo, uid, _resolve_admin_email(args.admin_email))
        return

    if args.command == "reject":
        await _reject(repo, uid, _resolve_admin_email(args.admin_email), args.reason)
        return

    if args.command == "revoke":
        await _revoke(repo, uid, _resolve_admin_email(args.admin_email), args.reason)
        return

    if args.command == "resync-sheet":
        await _resync_sheet(repo, uid)
        return


if __name__ == "__main__":
    asyncio.run(main())
