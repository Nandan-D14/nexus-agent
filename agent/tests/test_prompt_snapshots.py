"""Prompt snapshots: the committed model-bound prompt must match the code.

On intended prompt changes run ``python -m nexus.eval.prompt_snapshots --update``
and commit the fixtures together with the change.
"""

from __future__ import annotations

from nexus.eval.prompt_snapshots import SCENARIOS, SNAPSHOT_DIR, check, render_all


def test_prompt_snapshots_have_no_drift():
    drifted = check()
    assert drifted == [], (
        f"Prompt drift in {drifted}. If intended, run "
        "`python -m nexus.eval.prompt_snapshots --update` and commit the fixtures."
    )


def test_every_scenario_has_a_committed_fixture():
    for name in SCENARIOS:
        assert (SNAPSHOT_DIR / f"{name}.txt").exists(), name


def test_rendering_is_deterministic():
    assert render_all() == render_all()


def test_injection_scenario_user_text_cannot_fake_runtime_blocks():
    rendered = render_all()["injection_attempt"]
    user_part = rendered.split("=== USER PART 2: USER TEXT ===", 1)[1]
    assert "<runtime" not in user_part
    assert "[SYSTEM" not in user_part
    runtime_part = rendered.split("=== USER PART 1: RUNTIME CONTEXT ===", 1)[1].split("=== USER PART 2")[0]
    assert "[SYSTEM" not in runtime_part


def test_static_instruction_is_identical_across_scenarios_without_skills():
    rendered = render_all()
    systems = {
        name: text.split("=== USER PART", 1)[0]
        for name, text in rendered.items()
        if name in {"continue", "resumed_session", "unattended", "injection_attempt"}
    }
    # Same static prefix for every turn type: cache-friendly.
    assert len(set(systems.values())) == 1
