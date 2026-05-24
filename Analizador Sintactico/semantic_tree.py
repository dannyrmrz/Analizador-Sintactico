"""
semantic_tree.py
================
Arbol semantico/parse tree producido por los parsers YAPar.

El arbol conserva la derivacion reconocida por LL(1), SLR(1) o LALR(1):
los no terminales son nodos internos y los terminales guardan token,
lexema, linea y columna cuando vienen del lexer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    from .token_stream import Token
    from .yalp_parser import EPSILON
except ImportError:  # pragma: no cover
    from token_stream import Token
    from yalp_parser import EPSILON


@dataclass
class SemanticNode:
    """Nodo del arbol semantico YAPar."""

    symbol: str
    lexeme: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    children: List["SemanticNode"] = field(default_factory=list)

    @classmethod
    def terminal(cls, token: Token) -> "SemanticNode":
        return cls(
            symbol=token.type,
            lexeme=token.lexeme,
            line=None if token.line < 0 else token.line,
            column=None if token.col < 0 else token.col,
        )

    @classmethod
    def epsilon(cls) -> "SemanticNode":
        return cls(symbol=EPSILON)

    def add_child(self, child: "SemanticNode") -> None:
        self.children.append(child)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {"symbol": self.symbol}
        if self.lexeme is not None:
            data["lexeme"] = self.lexeme
        if self.line is not None:
            data["line"] = self.line
        if self.column is not None:
            data["column"] = self.column
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SemanticNode":
        """Reconstruye un nodo desde la representacion JSON exportada."""
        children_data = data.get("children", [])
        return cls(
            symbol=str(data["symbol"]),
            lexeme=None if "lexeme" not in data else str(data["lexeme"]),
            line=_optional_int(data.get("line")),
            column=_optional_int(data.get("column")),
            children=[
                cls.from_dict(child)
                for child in children_data
                if isinstance(child, dict)
            ],
        )

    def pretty(self, indent: str = "", is_last: bool = True) -> str:
        branch = "`- " if is_last else "|- "
        label = self.symbol
        if self.lexeme is not None:
            label += f" {self.lexeme!r}"
        if self.line is not None and self.column is not None:
            label += f" @ {self.line}:{self.column}"

        lines = [indent + branch + label]
        child_indent = indent + ("   " if is_last else "|  ")
        for index, child in enumerate(self.children):
            lines.append(child.pretty(child_indent, index == len(self.children) - 1))
        return "\n".join(lines)

    def to_dot(self) -> str:
        lines = [
            "digraph SemanticTree {",
            '  node [shape=box, fontname="Consolas"];',
            "  edge [fontname=\"Consolas\"];",
        ]
        ids: Dict[int, str] = {}

        def visit(node: "SemanticNode") -> None:
            node_id = ids.setdefault(id(node), f"n{len(ids)}")
            lines.append(f'  {node_id} [label="{_dot_escape(_node_label(node))}"];')
            for child in node.children:
                child_id = ids.setdefault(id(child), f"n{len(ids)}")
                visit(child)
                lines.append(f"  {node_id} -> {child_id};")

        visit(self)
        lines.append("}")
        return "\n".join(lines) + "\n"

    def walk(self) -> Iterable[tuple["SemanticNode", int]]:
        """Itera el arbol en preorden junto con la profundidad de cada nodo."""
        yield from _walk(self, 0)


def write_tree_json(tree: SemanticNode, path: str) -> None:
    Path(path).write_text(
        json.dumps(tree.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def write_tree_dot(tree: SemanticNode, path: str) -> None:
    Path(path).write_text(tree.to_dot(), encoding="utf-8", newline="\n")


def read_tree_json(path: str) -> SemanticNode:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El JSON del arbol debe tener un objeto raiz.")
    return SemanticNode.from_dict(data)


def forest_pretty(trees: Iterable[SemanticNode]) -> str:
    return "\n".join(tree.pretty() for tree in trees)


def _node_label(node: SemanticNode) -> str:
    label = node.symbol
    if node.lexeme is not None:
        label += f"\\n{node.lexeme!r}"
    if node.line is not None and node.column is not None:
        label += f"\\n{node.line}:{node.column}"
    return label


def _dot_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _walk(node: SemanticNode, depth: int) -> Iterable[tuple[SemanticNode, int]]:
    yield node, depth
    for child in node.children:
        yield from _walk(child, depth + 1)
