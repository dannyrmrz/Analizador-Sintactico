"""
lalr_parser.py
==============
Construccion de tabla y parser LALR(1).

El algoritmo implementado es el clasico:
  1. construir la coleccion canonica LR(1);
  2. fusionar estados con el mismo core LR(0);
  3. construir ACTION/GOTO desde los estados fusionados;
  4. detectar conflictos shift/reduce y reduce/reduce.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from .ll1_analyzer import LL1Analyzer
    from .lr0_automaton import LRProduction, _dot_escape, _unique_augmented_start
    from .token_stream import Token, TokenStream
    from .yalp_parser import END_MARKER, EPSILON, YalpSpec
except ImportError:  # pragma: no cover
    from ll1_analyzer import LL1Analyzer
    from lr0_automaton import LRProduction, _dot_escape, _unique_augmented_start
    from token_stream import Token, TokenStream
    from yalp_parser import END_MARKER, EPSILON, YalpSpec


@dataclass(frozen=True, order=True)
class LR1Item:
    """Item LR(1): A -> alpha . beta, a."""

    production_index: int
    dot: int = 0
    lookahead: str = END_MARKER

    @property
    def core(self) -> Tuple[int, int]:
        return (self.production_index, self.dot)


@dataclass(frozen=True)
class LALRStatus:
    implemented: bool
    summary: str
    pending: List[str]


@dataclass
class LR1State:
    """Estado de la coleccion canonica LR(1)."""

    id: int
    items: frozenset[LR1Item]

    @property
    def core(self) -> frozenset[Tuple[int, int]]:
        return frozenset(item.core for item in self.items)


@dataclass
class LALRAction:
    """Accion ACTION de una tabla LALR(1)."""

    kind: str
    target: Optional[int] = None
    production_index: Optional[int] = None

    def text(self, productions: Sequence[LRProduction]) -> str:
        if self.kind == "shift":
            return f"s{self.target}"
        if self.kind == "reduce" and self.production_index is not None:
            return f"r{self.production_index} ({productions[self.production_index].text()})"
        if self.kind == "accept":
            return "acc"
        return self.kind


@dataclass
class LALRConflict:
    """Conflicto detectado al llenar ACTION."""

    state: int
    terminal: str
    existing: LALRAction
    new: LALRAction
    conflict_type: str

    def text(self, productions: Sequence[LRProduction]) -> str:
        return (
            f"{self.conflict_type} en ACTION[{self.state}, {self.terminal}]: "
            f"{self.existing.text(productions)} vs {self.new.text(productions)}"
        )


@dataclass
class LALRParseStep:
    """Un paso del parser LALR."""

    stack: List[int]
    lookahead: str
    action: str


@dataclass
class LALRParseResult:
    """Resultado del parser LALR."""

    accepted: bool
    steps: List[LALRParseStep] = field(default_factory=list)
    error: Optional[str] = None
    token: Optional[Token] = None
    expected: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)
    recovered: bool = False


@dataclass
class LALRParser:
    """Constructor de coleccion LR(1), tabla y parser LALR(1)."""

    spec: YalpSpec
    augmented_start: str = field(init=False)
    productions: List[LRProduction] = field(init=False)
    lr1_states: List[LR1State] = field(init=False)
    lr1_transitions: Dict[Tuple[int, str], int] = field(init=False)
    states: List[LR1State] = field(init=False)
    transitions: Dict[Tuple[int, str], int] = field(init=False)
    action: Dict[int, Dict[str, LALRAction]] = field(init=False)
    goto_table: Dict[int, Dict[str, int]] = field(init=False)
    conflicts: List[LALRConflict] = field(init=False)
    first: Dict[str, Set[str]] = field(init=False)
    non_terminals: List[str] = field(init=False)
    terminals: List[str] = field(init=False)

    def __post_init__(self) -> None:
        analyzer = LL1Analyzer(self.spec)
        self.first = analyzer.first
        self.augmented_start = _unique_augmented_start(self.spec)
        self.productions = _build_lr_productions(self.spec, self.augmented_start)
        self.non_terminals = [self.augmented_start] + list(self.spec.non_terminals)
        self.terminals = sorted(self.spec.terminals)
        self.lr1_states = []
        self.lr1_transitions = {}
        self.states = []
        self.transitions = {}
        self.action = {}
        self.goto_table = {}
        self.conflicts = []
        self._build_canonical_lr1_collection()
        self._merge_lr1_states_by_core()
        self._build_tables()

    @property
    def is_lalr1(self) -> bool:
        return not self.conflicts

    def closure(self, items: Iterable[LR1Item]) -> frozenset[LR1Item]:
        """closure(I) para items LR(1)."""
        closure_set: Set[LR1Item] = set(items)
        changed = True
        while changed:
            changed = False
            for item in list(closure_set):
                symbol = self.symbol_after_dot(item)
                if symbol is None or symbol not in self.non_terminals:
                    continue

                production = self.productions[item.production_index]
                beta = list(production.rhs[item.dot + 1 :])
                lookaheads = self.first_of_sequence(beta + [item.lookahead]) - {EPSILON}

                for next_production in self.productions_for(symbol):
                    for lookahead in sorted(lookaheads):
                        new_item = LR1Item(next_production.index, 0, lookahead)
                        if new_item not in closure_set:
                            closure_set.add(new_item)
                            changed = True
        return frozenset(sorted(closure_set))

    def goto(self, items: Iterable[LR1Item], symbol: str) -> frozenset[LR1Item]:
        """goto(I, X): mueve el punto sobre X y aplica closure."""
        moved = []
        for item in items:
            if self.symbol_after_dot(item) == symbol:
                moved.append(LR1Item(item.production_index, item.dot + 1, item.lookahead))
        if not moved:
            return frozenset()
        return self.closure(moved)

    def symbol_after_dot(self, item: LR1Item) -> Optional[str]:
        production = self.productions[item.production_index]
        if item.dot >= len(production.rhs):
            return None
        return production.rhs[item.dot]

    def is_complete(self, item: LR1Item) -> bool:
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

    def first_of_sequence(self, symbols: Sequence[str]) -> Set[str]:
        if not symbols:
            return {EPSILON}

        result: Set[str] = set()
        all_can_be_epsilon = True
        for symbol in symbols:
            symbol_first = self.first.get(symbol, {symbol})
            result.update(symbol_first - {EPSILON})
            if EPSILON not in symbol_first:
                all_can_be_epsilon = False
                break
        if all_can_be_epsilon:
            result.add(EPSILON)
        return result

    def parse(
        self,
        tokens: Sequence[Token] | TokenStream,
        verbose: bool = False,
        recover: bool = False,
    ) -> LALRParseResult:
        if self.conflicts:
            return LALRParseResult(
                accepted=False,
                error="La gramatica no es LALR(1); hay conflictos shift/reduce o reduce/reduce.",
            )

        stream = tokens if isinstance(tokens, TokenStream) else TokenStream(list(tokens))
        stack: List[int] = [0]
        steps: List[LALRParseStep] = []
        errors: List[str] = []
        recovered = False

        while True:
            state = stack[-1]
            lookahead = stream.current
            lookahead_type = _normalize_eof_type(lookahead.type)
            action = self.action.get(state, {}).get(lookahead_type)

            if action is None:
                expected = set(self.action.get(state, {}))
                message = _unexpected_token_message(
                    lookahead,
                    expected,
                    f"No existe accion para ACTION[{state}, {lookahead_type}]",
                )
                if not recover:
                    return LALRParseResult(
                        accepted=False,
                        steps=steps,
                        error=message,
                        token=lookahead,
                        expected=expected,
                    )

                errors.append(message)
                recovered = True
                if not _recover_lr_stack_and_stream(stack, stream, self.action):
                    return LALRParseResult(
                        accepted=False,
                        steps=steps,
                        error=message,
                        token=lookahead,
                        expected=expected,
                        errors=errors,
                        recovered=recovered,
                    )
                continue

            _append_step(steps, verbose, list(stack), lookahead_type, action.text(self.productions))

            if action.kind == "shift":
                assert action.target is not None
                stack.append(action.target)
                stream.consume()
                continue

            if action.kind == "reduce":
                assert action.production_index is not None
                production = self.productions[action.production_index]
                for _ in production.rhs:
                    if len(stack) == 1:
                        message = f"Stack invalido al reducir {production.text()}."
                        return LALRParseResult(
                            accepted=False,
                            steps=steps,
                            error=message,
                            token=lookahead,
                            errors=errors + [message] if recover else errors,
                            recovered=recovered,
                        )
                    stack.pop()
                goto_state = self.goto_table.get(stack[-1], {}).get(production.lhs)
                if goto_state is None:
                    message = (
                        f"No existe GOTO[{stack[-1]}, {production.lhs}] "
                        f"despues de reducir {production.text()}."
                    )
                    return LALRParseResult(
                        accepted=False,
                        steps=steps,
                        error=message,
                        token=lookahead,
                        errors=errors + [message] if recover else errors,
                        recovered=recovered,
                    )
                stack.append(goto_state)
                continue

            if action.kind == "accept":
                return LALRParseResult(
                    accepted=not errors,
                    steps=steps,
                    error=errors[0] if errors else None,
                    errors=errors,
                    recovered=recovered,
                )

            message = f"Accion LALR desconocida: {action.kind}"
            return LALRParseResult(
                accepted=False,
                steps=steps,
                error=message,
                token=lookahead,
                errors=errors + [message] if recover else errors,
                recovered=recovered,
            )

    def action_entries(self) -> List[Tuple[int, str, LALRAction]]:
        entries: List[Tuple[int, str, LALRAction]] = []
        for state in sorted(self.action):
            for terminal in sorted(self.action[state]):
                entries.append((state, terminal, self.action[state][terminal]))
        return entries

    def goto_entries(self) -> List[Tuple[int, str, int]]:
        entries: List[Tuple[int, str, int]] = []
        for state in sorted(self.goto_table):
            for non_terminal in sorted(self.goto_table[state]):
                entries.append((state, non_terminal, self.goto_table[state][non_terminal]))
        return entries

    def format_item(self, item: LR1Item) -> str:
        production = self.productions[item.production_index]
        rhs = list(production.rhs)
        rhs.insert(item.dot, ".")
        rhs_text = " ".join(rhs) if rhs else "."
        return f"{production.lhs} -> {rhs_text}, {item.lookahead}"

    def format_state(self, state_id: int) -> str:
        state = self.states[state_id]
        lines = [f"I{state.id}:"]
        lines.extend(self.format_item(item) for item in sorted(state.items))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, object]:
        return {
            "isLALR1": self.is_lalr1,
            "augmentedStart": self.augmented_start,
            "conflicts": [conflict.text(self.productions) for conflict in self.conflicts],
            "canonicalLR1States": len(self.lr1_states),
            "lalrStates": len(self.states),
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
            "action": [
                {
                    "state": state,
                    "terminal": terminal,
                    "action": action.text(self.productions),
                }
                for state, terminal, action in self.action_entries()
            ],
            "goto": [
                {"state": state, "nonTerminal": nt, "to": target}
                for state, nt, target in self.goto_entries()
            ],
        }

    def to_dot(self) -> str:
        lines = ["digraph LALR {", "  rankdir=LR;", '  node [shape=box, fontname="Consolas"];']
        for state in self.states:
            label = _dot_escape(self.format_state(state.id))
            lines.append(f'  I{state.id} [label="{label}"];')
        for (src, symbol), dst in sorted(self.transitions.items()):
            lines.append(f'  I{src} -> I{dst} [label="{_dot_escape(symbol)}"];')
        lines.append("}")
        return "\n".join(lines) + "\n"

    def write_dot(self, path: str) -> None:
        Path(path).write_text(self.to_dot(), encoding="utf-8", newline="\n")

    def _build_canonical_lr1_collection(self) -> None:
        start_items = self.closure([LR1Item(0, 0, END_MARKER)])
        state_ids: Dict[frozenset[LR1Item], int] = {}

        def add_state(items: frozenset[LR1Item]) -> int:
            existing = state_ids.get(items)
            if existing is not None:
                return existing
            state_id = len(self.lr1_states)
            state_ids[items] = state_id
            self.lr1_states.append(LR1State(state_id, items))
            return state_id

        add_state(start_items)
        queue = [0]
        while queue:
            state_id = queue.pop(0)
            items = self.lr1_states[state_id].items
            for symbol in self.grammar_symbols():
                target_items = self.goto(items, symbol)
                if not target_items:
                    continue
                known = target_items in state_ids
                target_id = add_state(target_items)
                self.lr1_transitions[(state_id, symbol)] = target_id
                if not known:
                    queue.append(target_id)

    def _merge_lr1_states_by_core(self) -> None:
        core_to_merged_id: Dict[frozenset[Tuple[int, int]], int] = {}
        old_to_merged: Dict[int, int] = {}
        merged_items: Dict[int, Set[LR1Item]] = {}

        for state in self.lr1_states:
            core = state.core
            if core not in core_to_merged_id:
                merged_id = len(core_to_merged_id)
                core_to_merged_id[core] = merged_id
                merged_items[merged_id] = set()
            merged_id = core_to_merged_id[core]
            old_to_merged[state.id] = merged_id
            merged_items[merged_id].update(state.items)

        self.states = [
            LR1State(state_id, frozenset(sorted(merged_items[state_id])))
            for state_id in range(len(merged_items))
        ]

        for (src, symbol), dst in sorted(self.lr1_transitions.items()):
            merged_src = old_to_merged[src]
            merged_dst = old_to_merged[dst]
            existing = self.transitions.get((merged_src, symbol))
            if existing is not None and existing != merged_dst:
                # En una coleccion LR(1) valida, estados con el mismo core tienen
                # transiciones compatibles. Si aparece esta situacion, conservar el
                # primer destino mantiene la tabla determinista y el conflicto real
                # se reflejara en ACTION.
                continue
            self.transitions[(merged_src, symbol)] = merged_dst

    def _build_tables(self) -> None:
        self.action = {state.id: {} for state in self.states}
        self.goto_table = {state.id: {} for state in self.states}

        for (state, symbol), target in self.transitions.items():
            if symbol in self.spec.terminals:
                self._add_action(state, symbol, LALRAction("shift", target=target))
            elif symbol in self.spec.non_terminals:
                self.goto_table[state][symbol] = target

        for state in self.states:
            for item in state.items:
                if not self.is_complete(item):
                    continue
                production = self.productions[item.production_index]
                if production.lhs == self.augmented_start:
                    self._add_action(state.id, END_MARKER, LALRAction("accept"))
                    continue
                self._add_action(
                    state.id,
                    item.lookahead,
                    LALRAction("reduce", production_index=production.index),
                )

    def _add_action(self, state: int, terminal: str, action: LALRAction) -> None:
        row = self.action.setdefault(state, {})
        existing = row.get(terminal)
        if existing is None:
            row[terminal] = action
            return
        if existing == action:
            return
        conflict_type = _conflict_type(existing, action)
        self.conflicts.append(
            LALRConflict(
                state=state,
                terminal=terminal,
                existing=existing,
                new=action,
                conflict_type=conflict_type,
            )
        )


def lalr_status() -> LALRStatus:
    """Estado resumido de la implementacion LALR actual."""
    return LALRStatus(
        implemented=True,
        summary="LALR(1) implementado con coleccion LR(1), fusion por core LR(0) y tabla ACTION/GOTO.",
        pending=[],
    )


def build_lalr_table(spec: YalpSpec) -> LALRParser:
    """Construye y devuelve el parser/tabla LALR(1) para spec."""
    return LALRParser(spec)


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


def _conflict_type(existing: LALRAction, new: LALRAction) -> str:
    kinds = {existing.kind, new.kind}
    if "shift" in kinds and "reduce" in kinds:
        return "shift/reduce conflict"
    if existing.kind == "reduce" and new.kind == "reduce":
        return "reduce/reduce conflict"
    return "/".join(sorted(kinds)) + " conflict"


def _append_step(
    steps: List[LALRParseStep],
    verbose: bool,
    stack: List[int],
    lookahead: str,
    action: str,
) -> None:
    if verbose:
        steps.append(LALRParseStep(stack=stack, lookahead=lookahead, action=action))


def _normalize_eof_type(token_type: str) -> str:
    return END_MARKER if token_type in {END_MARKER, "EOF"} else token_type


def _unexpected_token_message(token: Token, expected: Set[str], detail: str) -> str:
    expected_text = ", ".join(sorted(expected)) if expected else "(ninguno)"
    found = _normalize_eof_type(token.type)
    if found == END_MARKER:
        found_text = "EOF"
    else:
        found_text = f"{token.type} ({token.lexeme!r})"
    return (
        f"{detail}. Se encontro {found_text} en linea {token.line}, "
        f"columna {token.column}. Esperado: {expected_text}."
    )


def _recover_lr_stack_and_stream(
    stack: List[int],
    stream: TokenStream,
    action: Dict[int, Dict[str, LALRAction]],
) -> bool:
    """Recuperacion panic-mode: descarta tokens o estados hasta hallar accion."""
    while True:
        state = stack[-1]
        lookahead_type = _normalize_eof_type(stream.current.type)
        if action.get(state, {}).get(lookahead_type) is not None:
            return True
        if lookahead_type != END_MARKER:
            stream.consume()
            continue
        if len(stack) > 1:
            stack.pop()
            continue
        return False
