"""tests/test_dynamic_prompts.py — dynamic prompt expansion engine tests"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dynamic_prompts as dp


@pytest.fixture(autouse=True)
def clear_cache():
    dp._wildcard_cache.clear()
    yield
    dp._wildcard_cache.clear()


@pytest.fixture
def wildcards_dir(tmp_path):
    d = tmp_path / "wildcards"
    d.mkdir()
    return d


def _write_wildcard(wildcards_dir: Path, name: str, lines):
    (wildcards_dir / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ #
# {a|b|c} expansion
# ------------------------------------------------------------------ #


def test_simple_group_returns_one_option():
    for _ in range(20):
        result = dp.expand_prompt("{a|b|c}")
        assert result in ("a", "b", "c")


def test_group_within_text():
    for _ in range(20):
        result = dp.expand_prompt("a {red|blue} dress")
        assert result in ("a red dress", "a blue dress")


def test_nested_group():
    for _ in range(30):
        result = dp.expand_prompt("{a|{b|c}}")
        assert result in ("a", "b", "c")


def test_deeply_nested_group():
    for _ in range(30):
        result = dp.expand_prompt("{a|{b|{c|d}}}")
        assert result in ("a", "b", "c", "d")


# ------------------------------------------------------------------ #
# __wildcard__ loading
# ------------------------------------------------------------------ #


def test_wildcard_loads_from_file(wildcards_dir):
    _write_wildcard(wildcards_dir, "colors", ["red", "green", "blue"])
    for _ in range(20):
        result = dp.expand_prompt("__colors__", wildcards_dir=wildcards_dir)
        assert result in ("red", "green", "blue")


def test_wildcard_strips_empty_lines(wildcards_dir):
    _write_wildcard(wildcards_dir, "colors", ["red", "", "  ", "blue"])
    for _ in range(20):
        result = dp.expand_prompt("__colors__", wildcards_dir=wildcards_dir)
        assert result in ("red", "blue")


def test_missing_wildcard_file_returns_placeholder(wildcards_dir):
    result = dp.expand_prompt("__does_not_exist__", wildcards_dir=wildcards_dir)
    assert result == "__does_not_exist__"


def test_wildcard_combined_with_group(wildcards_dir):
    _write_wildcard(wildcards_dir, "hair", ["blonde", "brunette"])
    for _ in range(20):
        result = dp.expand_prompt("{a|b} __hair__", wildcards_dir=wildcards_dir)
        parts = result.split(" ", 1)
        assert parts[0] in ("a", "b")
        assert parts[1] in ("blonde", "brunette")


# ------------------------------------------------------------------ #
# Combinatorial expansion
# ------------------------------------------------------------------ #


def test_combinatorial_generates_correct_count():
    results = dp.expand_prompt_combinatorial("{a|b|c}")
    assert sorted(results) == ["a", "b", "c"]


def test_combinatorial_multiple_groups():
    results = dp.expand_prompt_combinatorial("{a|b} {1|2|3}")
    assert len(results) == 6
    assert len(set(results)) == 6


def test_combinatorial_with_wildcard(wildcards_dir):
    _write_wildcard(wildcards_dir, "colors", ["red", "green", "blue"])
    results = dp.expand_prompt_combinatorial("{a|b} __colors__", wildcards_dir=wildcards_dir)
    assert len(results) == 6


def test_combinatorial_exceeds_max_raises():
    with pytest.raises(ValueError):
        dp.expand_prompt_combinatorial("{a|b|c|d|e} {1|2|3|4|5} {x|y|z}", max_combinations=10)


def test_combinatorial_within_max_ok():
    results = dp.expand_prompt_combinatorial("{a|b|c|d|e} {1|2}", max_combinations=100)
    assert len(results) == 10


# ------------------------------------------------------------------ #
# count_combinations
# ------------------------------------------------------------------ #


def test_count_combinations_simple():
    assert dp.count_combinations("{a|b|c}") == 3


def test_count_combinations_multiple_groups():
    assert dp.count_combinations("{a|b} {1|2|3}") == 6


def test_count_combinations_nested():
    assert dp.count_combinations("{a|{b|c|d}}") == 4


def test_count_combinations_no_groups():
    assert dp.count_combinations("just plain text") == 1


def test_count_combinations_with_wildcard(wildcards_dir):
    _write_wildcard(wildcards_dir, "colors", ["red", "green", "blue"])
    assert dp.count_combinations("__colors__", wildcards_dir=wildcards_dir) == 3


# ------------------------------------------------------------------ #
# Escaped braces
# ------------------------------------------------------------------ #


def test_escaped_braces_preserved():
    result = dp.expand_prompt(r"\{literal\}")
    assert result == "{literal}"


def test_escaped_braces_alongside_real_group():
    for _ in range(20):
        result = dp.expand_prompt(r"\{not a group\} {a|b}")
        assert result in (r"{not a group} a", r"{not a group} b")


def test_escaped_pipe_preserved():
    result = dp.expand_prompt(r"a\|b")
    assert result == "a|b"


# ------------------------------------------------------------------ #
# Empty groups
# ------------------------------------------------------------------ #


def test_empty_group_option():
    for _ in range(20):
        result = dp.expand_prompt("a{| b}")
        assert result in ("a", "a b")


def test_unterminated_group_does_not_crash():
    result = dp.expand_prompt("{a|b")
    assert result in ("a", "b")


# ------------------------------------------------------------------ #
# Seed determinism
# ------------------------------------------------------------------ #


def test_seed_is_deterministic():
    template = "{a|b|c|d|e} __colors__ {1|2|3}"
    r1 = dp.expand_prompt(template, seed=42)
    r2 = dp.expand_prompt(template, seed=42)
    assert r1 == r2


def test_different_seeds_can_differ():
    template = "{a|b|c|d|e|f|g|h|i|j}"
    results = {dp.expand_prompt(template, seed=s) for s in range(10)}
    assert len(results) > 1


def test_preview_seed_deterministic(wildcards_dir):
    _write_wildcard(wildcards_dir, "colors", ["red", "green", "blue"])
    template = "{a|b} __colors__"
    r1 = dp.preview_expansion(template, wildcards_dir=wildcards_dir, count=5, seed=7)
    r2 = dp.preview_expansion(template, wildcards_dir=wildcards_dir, count=5, seed=7)
    assert r1 == r2


def test_preview_returns_requested_count():
    results = dp.preview_expansion("{a|b|c}", count=5)
    assert len(results) == 5
