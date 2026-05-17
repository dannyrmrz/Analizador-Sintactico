"""
lr0_automaton.py
================
Construccion del automata LR(0) para una gramatica YAPar ya parseada.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from .yalp_parser import EPSILON, YalpSpec
except ImportError:  # pragma: no cover
    from yalp_parser import EPSILON, YalpSpec


@dataclass(frozen=True)
class LRProduction:
    """Produccion indexada usada por LR(0)/SLR."""

    index: int
    lhs: str
    rhs: Tuple[str, ...]
    source_index: Optional[int] = None

    def text(self) -> str:
        rhs_text = " ".join(self.rhs) if self.rhs else EPSILON
        return f"{self.lhs} -> {rhs_text}"


@dataclass(frozen=True, order=True)
class LR0Item:
    """Item LR(0): A -> alpha . beta."""

    production_index: int
    dot: int = 0


@dataclass
class LR0State:
    """Estado del automata LR(0)."""

    id: int
    items: frozenset[LR0Item]


@dataclass
class LR0Automaton:
    """Automata LR(0) completo."""

    spec: YalpSpec
    augmented_start: str
    productions: List[LRProduction]
    states: List[LR0State] = field(default_factory=list)
    transitions: Dict[Tuple[int, str], int] = field(default_factory=dict)
    non_terminals: List[str] = field(default_factory=list)
    terminals: List[str] = field(default_factory=list)

    @classmethod
    def build(cls, spec: YalpSpec) -> "LR0Automaton":
        augmented_start = _unique_augmented_start(spec)
        productions = _build_lr_productions(spec, augmented_start)
        automaton = cls(
            spec=spec,
            augmented_start=augmented_start,
            productions=productions,
            non_terminals=[augmented_start] + list(spec.non_terminals),
            terminals=sorted(spec.terminals),
        )
        automaton._build_canonical_collection()
        return automaton

    def closure(self, items: Iterable[LR0Item]) -> frozenset[LR0Item]:
        """closure(I) para items LR(0)."""
        closure_set: Set[LR0Item] = set(items)
        changed = True
        while changed:
            changed = False
            for item in list(closure_set):
                symbol = self.symbol_after_dot(item)
                if symbol is None or symbol not in self.non_terminals:
                    continue
                for production in self.productions_for(symbol):
                    new_item = LR0Item(production.index, 0)
                    if new_item not in closure_set:
                        closure_set.add(new_item)
                        changed = True
        return frozenset(sorted(closure_set))

    def goto(self, items: Iterable[LR0Item], symbol: str) -> frozenset[LR0Item]:
        """goto(I, X): mueve el punto sobre X y aplica closure."""
        moved = []
        for item in items:
            if self.symbol_after_dot(item) == symbol:
                moved.append(LR0Item(item.production_index, item.dot + 1))
        if not moved:
            return frozenset()
        return self.closure(moved)

    def symbol_after_dot(self, item: LR0Item) -> Optional[str]:
        production = self.productions[item.production_index]
        if item.dot >= len(production.rhs):
            return None
        return production.rhs[item.dot]

    def is_complete(self, item: LR0Item) -> bool:
        return self.symbol_after_dot(item) is None

    def productions_for(self, lhs: str) -> List[LRProduction]:
        return [production for production in self.productions if production.lhs == lhs]

    def grammar_symbols(self) -> List[str]:
        symbols: List[str] = []
        for production in self.productions:
            for symbol in production.rhs:
                if symbol not in symbols:
                    symbols.append(symbol)
        return symbols

    def format_item(self, item: LR0Item) -> str:
        production = self.productions[item.production_index]
        rhs = list(production.rhs)
        rhs.insert(item.dot, ".")
        rhs_text = " ".join(rhs) if rhs else "."
        return f"{production.lhs} -> {rhs_text}"

    def format_state(self, state_id: int) -> str:
        state = self.states[state_id]
        lines = [f"I{state.id}:"]
        lines.extend(self.format_item(item) for item in sorted(state.items))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, object]:
        return {
            "augmentedStart": self.augmented_start,
            "productions": [
                {"index": p.index, "lhs": p.lhs, "rhs": list(p.rhs)}
                for p in self.productions
            ],
            "states": [
                {
                    "id": state.id,
                    "items": [self.format_item(item) for item in sorted(state.items)],
                }
                for state in self.states
            ],
            "transitions": [
                {"from": src, "symbol": symbol, "to": dst}
                for (src, symbol), dst in sorted(self.transitions.items())
            ],
        }

    def to_dot(self) -> str:
        lines = ["digraph LR0 {", "  rankdir=LR;", '  node [shape=box, fontname="Consolas"];']
        for state in self.states:
            label = _dot_escape(self.format_state(state.id))
            lines.append(f'  I{state.id} [label="{label}"];')
        for (src, symbol), dst in sorted(self.transitions.items()):
            lines.append(f'  I{src} -> I{dst} [label="{_dot_escape(symbol)}"];')
        lines.append("}")
        return "\n".join(lines) + "\n"

    def write_dot(self, path: str) -> None:
        Path(path).write_text(self.to_dot(), encoding="utf-8", newline="\n")

    def write_png(self, dot_path: str, png_path: Optional[str] = None) -> bool:
        png = png_path or (dot_path[:-4] + ".png" if dot_path.endswith(".dot") else dot_path + ".png")
        try:
            subprocess.run(
                ["dot", "-Tpng", dot_path, "-o", png],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def _build_canonical_collection(self) -> None:
        start_items = self.closure([LR0Item(0, 0)])
        state_ids: Dict[frozenset[LR0Item], int] = {}

        def add_state(items: frozenset[LR0Item]) -> int:
            existing = state_ids.get(items)
            if existing is not None:
                return existing
            state_id = len(self.states)
            state_ids[items] = state_id
            self.states.append(LR0State(state_id, items))
            return state_id

        add_state(start_items)
        queue = [0]
        while queue:
            state_id = queue.pop(0)
            items = self.states[state_id].items
            for symbol in self.grammar_symbols():
                target_items = self.goto(items, symbol)
                if not target_items:
                    continue
                known = target_items in state_ids
                target_id = add_state(target_items)
                self.transitions[(state_id, symbol)] = target_id
                if not known:
                    queue.append(target_id)


def _build_lr_productions(spec: YalpSpec, augmented_start: str) -> List[LRProduction]:
    productions = [
        LRProduction(
            index=0,
            lhs=augmented_start,
            rhs=(spec.start_symbol,),
            source_index=None,
        )
    ]
    for index, production in enumerate(spec.productions, start=1):
        rhs = tuple(symbol for symbol in production.rhs if symbol != EPSILON)
        productions.append(
            LRProduction(
                index=index,
                lhs=production.lhs,
                rhs=rhs,
                source_index=index - 1,
            )
        )
    return productions


def _unique_augmented_start(spec: YalpSpec) -> str:
    candidate = f"{spec.start_symbol}'"
    used = set(spec.non_terminals) | set(spec.terminals)
    while candidate in used:
        candidate += "'"
    return candidate


def _dot_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
