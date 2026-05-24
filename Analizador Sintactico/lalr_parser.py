"""
lalr_parser.py
==============
Tabla y parser LALR(1) construidos con items LR(1) y merge por core LR(0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from .ll1_analyzer import LL1Analyzer
    from .lr0_automaton import LR0Automaton, LRProduction
    from .semantic_tree import SemanticNode
    from .slr_parser import SLRAction, SLRConflict, SLRParseStep
    from .token_stream import Token, TokenStream
    from .yalp_parser import END_MARKER, EPSILON, YalpSpec
except ImportError:  # pragma: no cover
    from ll1_analyzer import LL1Analyzer
    from lr0_automaton import LR0Automaton, LRProduction
    from semantic_tree import SemanticNode
    from slr_parser import SLRAction, SLRConflict, SLRParseStep
    from token_stream import Token, TokenStream
    from yalp_parser import END_MARKER, EPSILON, YalpSpec


@dataclass(frozen=True)
class LR1Item:
    """Item LR(1): A -> alpha . beta, lookahead."""

    production_index: int
    dot: int
    lookahead: str

    @property
    def core(self) -> Tuple[int, int]:
        return self.production_index, self.dot


@dataclass
class LALRState:
    """Estado LALR ya fusionado por core LR(0)."""

    id: int
    items: frozenset[LR1Item]

    @property
    def core(self) -> frozenset[Tuple[int, int]]:
        return frozenset(item.core for item in self.items)


@dataclass
class LALRParseResult:
    accepted: bool
    steps: List[SLRParseStep] = field(default_factory=list)
    tree: Optional[SemanticNode] = None
    error: Optional[str] = None
    token: Optional[Token] = None
    expected: Set[str] = field(default_factory=set)


@dataclass(frozen=True)
class LALRStatus:
    implemented: bool
    summary: str
    pending: List[str]


@dataclass
class LALRParser:
    """Constructor de tabla y parser LALR(1)."""

    spec: YalpSpec
    base: LR0Automaton = field(init=False)
    productions: List[LRProduction] = field(init=False)
    augmented_start: str = field(init=False)
    first: Dict[str, Set[str]] = field(init=False)
    states: List[LALRState] = field(init=False)
    transitions: Dict[Tuple[int, str], int] = field(init=False)
    action: Dict[int, Dict[str, SLRAction]] = field(init=False)
    goto_table: Dict[int, Dict[str, int]] = field(init=False)
    conflicts: List[SLRConflict] = field(init=False)

    def __post_init__(self) -> None:
        self.base = LR0Automaton.build(self.spec)
        self.productions = self.base.productions
        self.augmented_start = self.base.augmented_start
        self.first = LL1Analyzer(self.spec).first
        self.states = []
        self.transitions = {}
        self.action = {}
        self.goto_table = {}
        self.conflicts = []
        self._build_lalr_collection()
        self._build_tables()

    @property
    def is_lalr1(self) -> bool:
        return not self.conflicts

    def closure(self, items: Iterable[LR1Item]) -> frozenset[LR1Item]:
        closure_set: Set[LR1Item] = set(items)
        changed = True
        while changed:
            changed = False
            for item in list(closure_set):
                symbol = self.symbol_after_dot(item)
                if symbol is None or symbol not in self.spec.non_terminals:
                    continue
                production = self.productions[item.production_index]
                beta = list(production.rhs[item.dot + 1 :]) + [item.lookahead]
                for lookahead in self.first_of_sequence(beta):
                    for next_production in self.productions_for(symbol):
                        new_item = LR1Item(next_production.index, 0, lookahead)
                        if new_item not in closure_set:
                            closure_set.add(new_item)
                            changed = True
        return frozenset(sorted(closure_set, key=lambda item: (item.production_index, item.dot, item.lookahead)))

    def goto(self, items: Iterable[LR1Item], symbol: str) -> frozenset[LR1Item]:
        moved = [
            LR1Item(item.production_index, item.dot + 1, item.lookahead)
            for item in items
            if self.symbol_after_dot(item) == symbol
        ]
        return self.closure(moved) if moved else frozenset()

    def parse(
        self,
        tokens: Sequence[Token] | TokenStream,
        verbose: bool = False,
    ) -> LALRParseResult:
        if self.conflicts:
            return LALRParseResult(
                accepted=False,
                error="La gramatica no es LALR(1); hay conflictos.",
            )

        stream = tokens if isinstance(tokens, TokenStream) else TokenStream(list(tokens))
        stack: List[int] = [0]
        node_stack: List[SemanticNode] = []
        steps: List[SLRParseStep] = []

        while True:
            state = stack[-1]
            lookahead = stream.current
            lookahead_type = END_MARKER if lookahead.type in {END_MARKER, "EOF"} else lookahead.type
            action = self.action.get(state, {}).get(lookahead_type)

            if action is None:
                expected = set(self.action.get(state, {}))
                return LALRParseResult(
                    accepted=False,
                    steps=steps,
                    tree=node_stack[-1] if node_stack else None,
                    error=_unexpected_token_message(
                        lookahead,
                        expected,
                        f"No existe accion para ACTION[{state}, {lookahead_type}]",
                    ),
                    token=lookahead,
                    expected=expected,
                )

            if verbose:
                steps.append(SLRParseStep(list(stack), lookahead_type, action.text(self.productions)))

            if action.kind == "shift":
                assert action.target is not None
                stack.append(action.target)
                node_stack.append(SemanticNode.terminal(lookahead))
                stream.consume()
                continue

            if action.kind == "reduce":
                assert action.production_index is not None
                production = self.productions[action.production_index]
                child_count = len(production.rhs)
                if child_count > len(node_stack):
                    return LALRParseResult(
                        accepted=False,
                        steps=steps,
                        tree=node_stack[-1] if node_stack else None,
                        error=f"Stack semantico invalido al reducir {production.text()}.",
                        token=lookahead,
                    )
                children = node_stack[-child_count:] if child_count else [SemanticNode.epsilon()]
                for _ in production.rhs:
                    stack.pop()
                if child_count:
                    del node_stack[-child_count:]
                goto_state = self.goto_table.get(stack[-1], {}).get(production.lhs)
                if goto_state is None:
                    return LALRParseResult(
                        accepted=False,
                        steps=steps,
                        tree=node_stack[-1] if node_stack else None,
                        error=(
                            f"No existe GOTO[{stack[-1]}, {production.lhs}] "
                            f"despues de reducir {production.text()}."
                        ),
                        token=lookahead,
                    )
                node_stack.append(SemanticNode(production.lhs, children=list(children)))
                stack.append(goto_state)
                continue

            if action.kind == "accept":
                return LALRParseResult(True, steps=steps, tree=node_stack[-1] if node_stack else None)

            return LALRParseResult(
                accepted=False,
                steps=steps,
                tree=node_stack[-1] if node_stack else None,
                error=f"Accion LALR desconocida: {action.kind}",
                token=lookahead,
            )

    def to_dict(self) -> Dict[str, object]:
        return {
            "isLALR1": self.is_lalr1,
            "conflicts": [conflict.text(self.productions) for conflict in self.conflicts],
            "states": [
                {
                    "id": state.id,
                    "items": [self.format_item(item) for item in sorted(state.items, key=lambda it: (it.production_index, it.dot, it.lookahead))],
                }
                for state in self.states
            ],
            "transitions": [
                {"from": src, "symbol": symbol, "to": dst}
                for (src, symbol), dst in sorted(self.transitions.items())
            ],
            "action": [
                {"state": state, "terminal": terminal, "action": action.text(self.productions)}
                for state in sorted(self.action)
                for terminal, action in sorted(self.action[state].items())
            ],
            "goto": [
                {"state": state, "nonTerminal": nt, "to": target}
                for state in sorted(self.goto_table)
                for nt, target in sorted(self.goto_table[state].items())
            ],
        }

    def symbol_after_dot(self, item: LR1Item) -> Optional[str]:
        production = self.productions[item.production_index]
        return production.rhs[item.dot] if item.dot < len(production.rhs) else None

    def productions_for(self, lhs: str) -> List[LRProduction]:
        return [production for production in self.productions if production.lhs == lhs]

    def first_of_sequence(self, symbols: Sequence[str]) -> Set[str]:
        result: Set[str] = set()
        if not symbols:
            return {EPSILON}
        for symbol in symbols:
            symbol_first = self.first.get(symbol, {symbol})
            result.update(symbol_first - {EPSILON})
            if EPSILON not in symbol_first:
                return result
        result.add(EPSILON)
        return result

    def format_item(self, item: LR1Item) -> str:
        production = self.productions[item.production_index]
        rhs = list(production.rhs)
        rhs.insert(item.dot, ".")
        rhs_text = " ".join(rhs) if rhs else "."
        return f"{production.lhs} -> {rhs_text}, {item.lookahead}"

    def _build_lalr_collection(self) -> None:
        canonical_states: List[frozenset[LR1Item]] = []
        canonical_transitions: Dict[Tuple[int, str], int] = {}
        state_ids: Dict[frozenset[LR1Item], int] = {}

        def add_state(items: frozenset[LR1Item]) -> int:
            existing = state_ids.get(items)
            if existing is not None:
                return existing
            state_id = len(canonical_states)
            state_ids[items] = state_id
            canonical_states.append(items)
            return state_id

        add_state(self.closure([LR1Item(0, 0, END_MARKER)]))
        queue = [0]
        while queue:
            state_id = queue.pop(0)
            for symbol in self.base.grammar_symbols():
                target_items = self.goto(canonical_states[state_id], symbol)
                if not target_items:
                    continue
                known = target_items in state_ids
                target_id = add_state(target_items)
                canonical_transitions[(state_id, symbol)] = target_id
                if not known:
                    queue.append(target_id)

        core_to_items: Dict[frozenset[Tuple[int, int]], Set[LR1Item]] = {}
        for items in canonical_states:
            core = frozenset(item.core for item in items)
            core_to_items.setdefault(core, set()).update(items)

        core_to_id: Dict[frozenset[Tuple[int, int]], int] = {}
        for core, items in core_to_items.items():
            state_id = len(self.states)
            core_to_id[core] = state_id
            self.states.append(LALRState(state_id, frozenset(items)))

        canonical_to_lalr = {
            index: core_to_id[frozenset(item.core for item in items)]
            for index, items in enumerate(canonical_states)
        }
        for (src, symbol), dst in canonical_transitions.items():
            self.transitions[(canonical_to_lalr[src], symbol)] = canonical_to_lalr[dst]

    def _build_tables(self) -> None:
        self.action = {state.id: {} for state in self.states}
        self.goto_table = {state.id: {} for state in self.states}

        for (state, symbol), target in self.transitions.items():
            if symbol in self.spec.terminals:
                self._add_action(state, symbol, SLRAction("shift", target=target))
            elif symbol in self.spec.non_terminals:
                self.goto_table[state][symbol] = target

        for state in self.states:
            for item in state.items:
                if self.symbol_after_dot(item) is not None:
                    continue
                production = self.productions[item.production_index]
                if production.lhs == self.augmented_start:
                    self._add_action(state.id, END_MARKER, SLRAction("accept"))
                else:
                    self._add_action(
                        state.id,
                        item.lookahead,
                        SLRAction("reduce", production_index=production.index),
                    )

    def _add_action(self, state: int, terminal: str, action: SLRAction) -> None:
        row = self.action.setdefault(state, {})
        existing = row.get(terminal)
        if existing is None:
            row[terminal] = action
            return
        if existing == action:
            return
        kinds = {existing.kind, action.kind}
        if "shift" in kinds and "reduce" in kinds:
            conflict_type = "shift/reduce conflict"
        elif existing.kind == "reduce" and action.kind == "reduce":
            conflict_type = "reduce/reduce conflict"
        else:
            conflict_type = "/".join(sorted(kinds)) + " conflict"
        self.conflicts.append(SLRConflict(state, terminal, existing, action, conflict_type))


def lalr_status() -> LALRStatus:
    return LALRStatus(
        implemented=True,
        summary="LALR(1) implementado con items LR(1), merge por core LR(0) y tabla ACTION/GOTO.",
        pending=[],
    )


def build_lalr_table(spec: YalpSpec) -> LALRParser:
    return LALRParser(spec)


def _unexpected_token_message(token: Token, expected: Set[str], detail: str) -> str:
    expected_text = ", ".join(sorted(expected)) if expected else "(ninguno)"
    found = END_MARKER if token.type in {END_MARKER, "EOF"} else token.type
    found_text = "EOF" if found == END_MARKER else f"{token.type} ({token.lexeme!r})"
    return (
        f"{detail}. Se encontro {found_text} en linea {token.line}, "
        f"columna {token.column}. Esperado: {expected_text}."
    )
