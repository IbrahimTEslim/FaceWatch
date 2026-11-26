"""
Smoke tests for Step 8: storage/app_tracker.py
Run from project root:
    python.exe tests\test_step8_app_tracker.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from storage.app_tracker import get_app_category, get_active_app, APP_CATEGORIES


def test_known_categories():
    cases = [
        ("chrome.exe",         "browser"),
        ("code.exe",           "editor"),
        ("slack.exe",          "communication"),
        ("steam.exe",          "game"),
        ("vlc.exe",            "media"),
        ("windowsterminal.exe","terminal"),
        ("winword.exe",        "document"),
    ]
    for proc, expected in cases:
        result = get_app_category(proc)
        assert result == expected, f"{proc}: expected {expected}, got {result}"
    print(f"  [OK] {len(cases)} known app categories correct")


def test_unknown_falls_back_to_other():
    result = get_app_category("somegame123.exe")
    assert result == "other"
    print("  [OK] Unknown process falls back to 'other'")


def test_category_lookup_is_case_insensitive():
    assert get_app_category("Chrome.EXE") == "browser"
    assert get_app_category("CODE.EXE")   == "editor"
    print("  [OK] Category lookup is case-insensitive")


def test_get_active_app_returns_tuple():
    proc, title = get_active_app()
    assert isinstance(proc, str)
    assert isinstance(title, str)
    assert len(proc) > 0
    print(f"  [OK] get_active_app() returned: proc='{proc}', title='{title[:40]}'")


def test_get_active_app_category_resolvable():
    proc, _ = get_active_app()
    category = get_app_category(proc)
    assert isinstance(category, str)
    print(f"  [OK] Active app '{proc}' resolved to category '{category}'")


def test_all_category_values_are_valid():
    valid = {"browser", "editor", "communication", "game", "media", "terminal", "document"}
    for proc, cat in APP_CATEGORIES.items():
        assert cat in valid, f"{proc} has invalid category '{cat}'"
    print(f"  [OK] All {len(APP_CATEGORIES)} entries have valid category values")


if __name__ == "__main__":
    print("\nStep 8 — App Tracker Smoke Tests\n")

    tests = [
        test_known_categories,
        test_unknown_falls_back_to_other,
        test_category_lookup_is_case_insensitive,
        test_get_active_app_returns_tuple,
        test_get_active_app_category_resolvable,
        test_all_category_values_are_valid,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
