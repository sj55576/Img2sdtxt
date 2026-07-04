"""Dynamic / wildcard prompt expansion engine.

Supported syntax:
  {a|b|c}        - randomly pick one option (nesting allowed: {a|{b|c}})
  __filename__   - randomly pick one line from data/wildcards/filename.txt
  \\{ \\} \\|      - escaped literals, kept as-is in the output
"""

import itertools
import logging
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger("img2sdtxt.dynamic_prompts")

DEFAULT_WILDCARDS_DIR = Path(__file__).parent / "data" / "wildcards"

# Sentinel used while parsing to represent escaped characters, restored at the end.
_ESCAPE_MAP = {"\\{": "\x00OPEN\x00", "\\}": "\x00CLOSE\x00", "\\|": "\x00PIPE\x00"}
_UNESCAPE_MAP = {v: k[1] for k, v in _ESCAPE_MAP.items()}

_WILDCARD_PATTERN = re.compile(r"__([a-zA-Z0-9_-]+)__")

# Node types produced by the parser.
Node = Union["TextNode", "GroupNode", "WildcardNode", "SequenceNode"]


class TextNode:
    """A literal fragment of text with no further expansion needed."""

    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        return f"TextNode({self.text!r})"


class WildcardNode:
    """A __name__ wildcard reference."""

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"WildcardNode({self.name!r})"


class GroupNode:
    """A {opt1|opt2|...} group. Each option is itself a SequenceNode."""

    def __init__(self, options: List["SequenceNode"]):
        self.options = options

    def __repr__(self):
        return f"GroupNode({self.options!r})"


class SequenceNode:
    """An ordered sequence of nodes (text / wildcard / group)."""

    def __init__(self, nodes: List[Node]):
        self.nodes = nodes

    def __repr__(self):
        return f"SequenceNode({self.nodes!r})"


def _preprocess_escapes(template: str) -> str:
    for escaped, sentinel in _ESCAPE_MAP.items():
        template = template.replace(escaped, sentinel)
    return template


def _postprocess_escapes(text: str) -> str:
    for sentinel, char in _UNESCAPE_MAP.items():
        text = text.replace(sentinel, char)
    return text


class _Parser:
    """Recursive-descent parser turning a template into a SequenceNode tree."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def parse(self) -> SequenceNode:
        seq = self._parse_sequence(top_level=True)
        return seq

    def _parse_sequence(self, top_level: bool) -> SequenceNode:
        nodes: List[Node] = []
        buf: List[str] = []

        def flush_buf():
            if buf:
                nodes.append(TextNode("".join(buf)))
                buf.clear()

        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == "{":
                flush_buf()
                nodes.append(self._parse_group())
            elif ch == "}":
                if top_level:
                    # Stray closing brace at top level: treat as literal.
                    buf.append(ch)
                    self.pos += 1
                else:
                    break
            elif ch == "|":
                if top_level:
                    buf.append(ch)
                    self.pos += 1
                else:
                    break
            else:
                buf.append(ch)
                self.pos += 1

        flush_buf()
        return self._merge_wildcards(nodes)

    def _merge_wildcards(self, nodes: List[Node]) -> SequenceNode:
        """Expand __name__ tokens found inside TextNodes into WildcardNodes."""
        result: List[Node] = []
        for node in nodes:
            if isinstance(node, TextNode):
                result.extend(self._split_text_wildcards(node.text))
            else:
                result.append(node)
        return SequenceNode(result)

    def _split_text_wildcards(self, text: str) -> List[Node]:
        parts: List[Node] = []
        last_end = 0
        for match in _WILDCARD_PATTERN.finditer(text):
            if match.start() > last_end:
                parts.append(TextNode(text[last_end : match.start()]))
            parts.append(WildcardNode(match.group(1)))
            last_end = match.end()
        if last_end < len(text):
            parts.append(TextNode(text[last_end:]))
        if not parts:
            parts.append(TextNode(""))
        return parts

    def _parse_group(self) -> GroupNode:
        assert self.text[self.pos] == "{"
        self.pos += 1  # consume '{'

        options: List[SequenceNode] = []
        options.append(self._parse_sequence(top_level=False))

        while self.pos < self.length and self.text[self.pos] == "|":
            self.pos += 1  # consume '|'
            options.append(self._parse_sequence(top_level=False))

        if self.pos < self.length and self.text[self.pos] == "}":
            self.pos += 1  # consume '}'
        # If unterminated (no closing brace), just accept what we have.

        return GroupNode(options)


def parse_template(template: str) -> SequenceNode:
    """Parse a dynamic prompt template into a node tree."""
    escaped = _preprocess_escapes(template)
    parser = _Parser(escaped)
    return parser.parse()


class WildcardCache:
    """In-memory cache of wildcard file contents, keyed by resolved directory."""

    def __init__(self):
        self._cache: Dict[str, List[str]] = {}

    def clear(self):
        self._cache.clear()

    def get_lines(self, name: str, wildcards_dir: Path) -> List[str]:
        key = f"{wildcards_dir}:{name}"
        if key in self._cache:
            return self._cache[key]

        file_path = wildcards_dir / f"{name}.txt"
        if not file_path.exists():
            logger.warning("Wildcard file not found: %s", file_path)
            lines: List[str] = []
        else:
            raw = file_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in raw.splitlines() if line.strip()]

        self._cache[key] = lines
        return lines


_wildcard_cache = WildcardCache()


def _resolve_wildcards_dir(wildcards_dir: Optional[Path]) -> Path:
    return wildcards_dir if wildcards_dir is not None else DEFAULT_WILDCARDS_DIR


def _render_random(node: Node, wildcards_dir: Path, rng: random.Random) -> str:
    if isinstance(node, TextNode):
        return node.text
    if isinstance(node, WildcardNode):
        lines = _wildcard_cache.get_lines(node.name, wildcards_dir)
        if not lines:
            return f"__{node.name}__"
        return rng.choice(lines)
    if isinstance(node, GroupNode):
        if not node.options:
            return ""
        chosen = rng.choice(node.options)
        return _render_random(chosen, wildcards_dir, rng)
    if isinstance(node, SequenceNode):
        return "".join(_render_random(child, wildcards_dir, rng) for child in node.nodes)
    raise TypeError(f"Unexpected node type: {type(node)}")


def _node_option_texts(node: Node, wildcards_dir: Path) -> List[str]:
    """Return all possible rendered strings for a node (used for combinatorial expansion)."""
    if isinstance(node, TextNode):
        return [node.text]
    if isinstance(node, WildcardNode):
        lines = _wildcard_cache.get_lines(node.name, wildcards_dir)
        if not lines:
            return [f"__{node.name}__"]
        return lines
    if isinstance(node, GroupNode):
        if not node.options:
            return [""]
        results: List[str] = []
        for option in node.options:
            results.extend(_sequence_option_texts(option, wildcards_dir))
        return results
    raise TypeError(f"Unexpected node type: {type(node)}")


def _sequence_option_texts(seq: SequenceNode, wildcards_dir: Path) -> List[str]:
    if not seq.nodes:
        return [""]
    per_node_options = [_node_option_texts(child, wildcards_dir) for child in seq.nodes]
    combos = ["".join(parts) for parts in itertools.product(*per_node_options)]
    return combos


def _count_node_combinations(node: Node, wildcards_dir: Path) -> int:
    if isinstance(node, TextNode):
        return 1
    if isinstance(node, WildcardNode):
        lines = _wildcard_cache.get_lines(node.name, wildcards_dir)
        return max(len(lines), 1)
    if isinstance(node, GroupNode):
        if not node.options:
            return 1
        return sum(_count_sequence_combinations(option, wildcards_dir) for option in node.options)
    raise TypeError(f"Unexpected node type: {type(node)}")


def _count_sequence_combinations(seq: SequenceNode, wildcards_dir: Path) -> int:
    total = 1
    for child in seq.nodes:
        total *= _count_node_combinations(child, wildcards_dir)
    return total


def expand_prompt(template: str, wildcards_dir: Optional[Path] = None, seed: Optional[int] = None) -> str:
    """Expand a dynamic prompt template, picking random options.

    Args:
        template: The prompt template with {a|b|c} and __wildcard__ syntax.
        wildcards_dir: Directory containing wildcard .txt files (default: data/wildcards).
        seed: Random seed for reproducibility (None = random).

    Returns:
        Expanded prompt string.
    """
    resolved_dir = _resolve_wildcards_dir(wildcards_dir)
    rng = random.Random(seed)
    tree = parse_template(template)
    result = _render_random(tree, resolved_dir, rng)
    return _postprocess_escapes(result)


def count_combinations(template: str, wildcards_dir: Optional[Path] = None) -> int:
    """Count the number of possible combinations without expanding.

    Returns the total number of unique expansions possible.
    """
    resolved_dir = _resolve_wildcards_dir(wildcards_dir)
    tree = parse_template(template)
    return _count_sequence_combinations(tree, resolved_dir)


def expand_prompt_combinatorial(
    template: str, wildcards_dir: Optional[Path] = None, max_combinations: int = 100
) -> List[str]:
    """Generate all combinations from a dynamic prompt template.

    Args:
        template: The prompt template.
        wildcards_dir: Directory containing wildcard .txt files.
        max_combinations: Maximum number of combinations to generate (safety limit).

    Returns:
        List of expanded prompt strings.

    Raises:
        ValueError: If estimated combinations exceed max_combinations.
    """
    resolved_dir = _resolve_wildcards_dir(wildcards_dir)
    tree = parse_template(template)

    estimated = _count_sequence_combinations(tree, resolved_dir)
    if estimated > max_combinations:
        raise ValueError(f"Estimated combinations ({estimated}) exceed max_combinations ({max_combinations}).")

    combos = _sequence_option_texts(tree, resolved_dir)
    return [_postprocess_escapes(c) for c in combos]


def preview_expansion(
    template: str, wildcards_dir: Optional[Path] = None, count: int = 5, seed: Optional[int] = None
) -> List[str]:
    """Generate a few sample expansions for preview purposes."""
    resolved_dir = _resolve_wildcards_dir(wildcards_dir)
    rng = random.Random(seed)
    tree = parse_template(template)
    results = []
    for _ in range(count):
        results.append(_postprocess_escapes(_render_random(tree, resolved_dir, rng)))
    return results
