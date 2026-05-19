"""Phase E gate — MQL5 Service scaffold (build 5320 ``#property service``).

W7.3 from the v1.0.1 audit: the kit must ship a Service-program
archetype so chartless background tasks (data collectors, REST
pollers, VPS canaries) have a first-class scaffold rather than being
shoehorned into an EA's OnTimer.
"""

from __future__ import annotations

from pathlib import Path


from vibecodekit_mql5 import build as build_mod

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = REPO_ROOT / "scaffolds" / "service" / "standalone"


# ─── preset registration ───────────────────────────────────────────────────

def test_service_preset_registered() -> None:
    assert "service" in build_mod.PRESETS
    assert build_mod.PRESETS["service"] == ["standalone"]


def test_service_preset_in_phase_e_bucket() -> None:
    """Service scaffolds belong in Phase E, not E or D — they're a
    post-deploy archetype.  Regression: pre-build-5320 the kit only
    had Phase-A and Phase-D presets, and adding the service slot in
    the wrong bucket would let Phase-A tests assume it ships with
    risk-guard wiring (it deliberately does not)."""
    assert "service" in build_mod.PHASE_E_PRESETS
    assert "service" not in build_mod.PHASE_A_PRESETS
    assert "service" not in build_mod.PHASE_D_PRESETS


# ─── scaffold files ────────────────────────────────────────────────────────

def test_service_scaffold_files_exist() -> None:
    assert SERVICE_DIR.is_dir()
    assert (SERVICE_DIR / "EAName.mq5").is_file()
    assert (SERVICE_DIR / "README.md").is_file()
    assert (SERVICE_DIR / "Sets" / "default.set").is_file()


def test_service_mq5_declares_property_service() -> None:
    text = (SERVICE_DIR / "EAName.mq5").read_text(encoding="utf-8")
    assert "#property service" in text, (
        "service scaffold must declare #property service (build 5320+)"
    )


def test_service_mq5_has_onstart_with_isstopped_loop() -> None:
    text = (SERVICE_DIR / "EAName.mq5").read_text(encoding="utf-8")
    assert "void OnStart(void)" in text
    assert "while(!IsStopped())" in text, (
        "service main loop must respect IsStopped() for clean shutdown"
    )


def test_service_mq5_carries_digits_tested_tag() -> None:
    text = (SERVICE_DIR / "EAName.mq5").read_text(encoding="utf-8")
    assert "digits-tested:" in text, (
        "service scaffold must carry the // digits-tested: meta tag "
        "(AP-21) so wizard renders pass lint"
    )


# ─── end-to-end build flow ─────────────────────────────────────────────────

def test_build_renders_service_scaffold(tmp_path: Path) -> None:
    req = build_mod.BuildRequest(
        preset="service",
        name="MyDataDaemon",
        symbol="EURUSD",
        tf="H1",
        stack="standalone",
        out_dir=tmp_path / "out",
        scaffolds_root=REPO_ROOT / "scaffolds",
        include_root=REPO_ROOT / "Include",
    )
    out = build_mod.build(req)
    rendered = (out / "MyDataDaemon.mq5").read_text(encoding="utf-8")
    assert "MyDataDaemon" in rendered
    assert "#property service" in rendered
    # Template placeholders must have been substituted out.
    assert "{{NAME}}" not in rendered
    assert "{{SYMBOL}}" not in rendered
    assert "{{TF}}" not in rendered


def test_service_preset_default_stack_is_standalone(tmp_path: Path) -> None:
    """The CLI picks the first stack when --stack is omitted."""
    rc = build_mod.main([
        "service", "--name", "Canary",
        "--symbol", "EURUSD", "--tf", "M5",
        "--out", str(tmp_path / "canary"),
    ])
    assert rc == 0
    assert (tmp_path / "canary" / "Canary.mq5").is_file()


def test_service_scaffold_does_not_call_ctrade() -> None:
    """Plan v5 §17: services never place orders.  If a future edit
    accidentally pastes CTrade into the service scaffold it would
    bypass the kit's risk-guard wiring silently — fail loudly."""
    text = (SERVICE_DIR / "EAName.mq5").read_text(encoding="utf-8")
    forbidden = ("CTrade", "OrderSend", "trade.Buy", "trade.Sell")
    for token in forbidden:
        assert token not in text, (
            f"service scaffold must not reference {token!r}"
        )


# ─── reference doc cross-link ──────────────────────────────────────────────

def test_service_readme_mentions_build_5320() -> None:
    text = (SERVICE_DIR / "README.md").read_text(encoding="utf-8")
    assert "5320" in text, "service README must pin minimum build 5320"
