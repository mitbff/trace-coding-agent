from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_order_demo_contains_reproducible_three_turn_fixture():
    demo = ROOT / "examples" / "order_demo"
    expected = {
        ".gitignore",
        "README.md",
        "order.py",
        "order_check.py",
        "pricing.py",
        "pricing_check.py",
        "requirements.txt",
    }

    assert {item.name for item in demo.iterdir()} == expected
    assert "price + price * discount_rate" in (demo / "pricing.py").read_text(encoding="utf-8")
    instructions = (demo / "README.md").read_text(encoding="utf-8")
    assert instructions.count("```text") == 3
    assert "python -m pytest -q pricing_check.py order_check.py" in instructions


def test_demo_scripts_enforce_safe_reset_and_readiness_checks():
    prepare = (ROOT / "scripts" / "prepare_demo.ps1").read_text(encoding="utf-8")
    check = (ROOT / "scripts" / "check_demo.ps1").read_text(encoding="utf-8")

    assert "Demo destination must stay inside" in prepare
    assert "AllowExternal" in prepare
    assert "Refusing to replace a drive root" in prepare
    assert "Refusing to replace the workspace root" in prepare
    assert "Expected the initial demo tests to fail" in prepare
    assert "OPENAI_API_KEY" in check
    assert "Get-NetTCPConnection" in check
