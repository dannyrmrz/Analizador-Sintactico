"""
slr_parser.py
=============
Tabla y parser SLR(1) construidos sobre el automata LR(0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from .ll1_analyzer import LL1Analyzer
    from .lr0_automaton import LR0Automaton, LRProduction
    from .token_stream import EOF_TOKEN, Token, TokenStream
    from .yalp_parser import END_MARKER, YalpSpec
except ImportError:  # pragma: no cover
    from ll1_analyzer import LL1Analyzer
    from lr0_automaton import LR0Automaton, LRProduction
    from token_stream import EOF_TOKEN, Token, TokenStream
    from yalp_parser import END_MARKER, YalpSpec


@dataclass(frozen=True)
class SLRAction:
    """Accion ACTION de una tabla SLR(1)."""

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
class SLRConflict:
    """Conflicto detectado al llenar ACTION."""

    state: int
    terminal: str
    existing: SLRAction
    new: SLRAction
    conflict_type: str

    def text(self, productions: Sequence[LRProduction]) -> str:
        return (
            f"{self.conflict_type} en ACTION[{self.state}, {self.terminal}]: "
            f"{self.existing.text(productions)} vs {self.new.text(productions)}"
        )


@dataclass
class SLRParseStep:
    """Un paso del parser SLR."""

    stack: List[int]
    lookahead: str
    action: str


@dataclass
class SLRParseResult:
    """Resultado del parser SLR."""

    accepted: bool
    steps: List[SLRParseStep] = field(default_factory=list)
    error: Optional[str] = None
    token: Optional[Token] = None
    expected: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)
    recovered: bool = False


@dataclass
class SLRParser:
    """Constructor de tabla y parser SLR(1)."""

    spec: YalpSpec
    automaton: LR0Automaton = field(init=False)
    action: Dict[int, Dict[str, SLRAction]] = field(init=False)
    goto_table: Dict[int, Dict[str, int]] = field(init=False)
    conflicts: List[SLRConflict] = field(init=False)
    follow: Dict[str, Set[str]] = field(init=False)

    def __post_init__(self) -> None:
        self.automaton = LR0Automaton.build(self.spec)
        self.follow = LL1Analyzer(self.spec).follow
        self.action = {state.id: {} for state in self.automaton.states}
        self.goto_table = {state.id: {} for state in self.automaton.states}
        self.conflicts = []
        self._build_tables()

    @property
    def is_slr1(self) -> bool:
        return not self.conflicts

    def parse(
        self,
        tokens: Sequence[Token] | TokenStream,
        verbose: bool = False,
        recover: bool = False,
    ) -> SLRParseResult:
        if self.conflicts:
            return SLRParseResult(
                accepted=False,
                error="La gramatica no es SLR(1); hay conflictos shift/reduce o reduce/reduce.",
            )

        stream = tokens if isinstance(tokens, TokenStream) else TokenStream(list(tokens))
        stack: List[int] = [0]
        steps: List[SLRParseStep] = []
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
                    return SLRParseResult(
                        accepted=False,
                        steps=steps,
                        error=message,
                        token=lookahead,
                        expected=expected,
                    )
                errors.append(message)
                recovered = True
                if not _recover_lr_stack_and_stream(stack, stream, self.action):
                    return SLRParseResult(
                        accepted=False,
                        steps=steps,
                        error=message,
                        token=lookahead,
                        expected=expected,
                        errors=errors,
                        recovered=recovered,
                    )
                continue

            _append_step(steps, verbose, list(stack), lookahead_type, action.text(self.automaton.productions))

            if action.kind == "shift":
                assert action.target is not None
                stack.append(action.target)
                stream.consume()
                continue

            if action.kind == "reduce":
                assert action.production_index is not None
                production = self.automaton.productions[action.production_index]
                for _ in production.rhs:
                    if len(stack) == 1:
                        message = f"Stack invalido al reducir {production.text()}."
                        return SLRParseResult(
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
                    return SLRParseResult(
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
                return SLRParseResult(
                    accepted=not errors,
                    steps=steps,
                    error=errors[0] if errors else None,
                    errors=errors,
                    recovered=recovered,
                )

            message = f"Accion SLR desconocida: {action.kind}"
            return SLRParseResult(
                accepted=False,
                steps=steps,
                error=message,
                token=lookahead,
                errors=errors + [message] if recover else errors,
                recovered=recovered,
            )

    def action_entries(self) -> List[Tuple[int, str, SLRAction]]:
        entries: List[Tuple[int, str, SLRAction]] = []
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

    def to_dict(self) -> Dict[str, object]:
        return {
            "isSLR1": self.is_slr1,
            "conflicts": [conflict.text(self.automaton.productions) for conflict in self.conflicts],
            "action": [
                {
                    "state": state,
                    "terminal": terminal,
                    "action": action.text(self.automaton.productions),
                }
                for state, terminal, action in self.action_entries()
            ],
            "goto": [
                {"state": state, "nonTerminal": nt, "to": target}
                for state, nt, target in self.goto_entries()
            ],
        }

    def _build_tables(self) -> None:
        for (state, symbol), target in self.automaton.transitions.items():
            if symbol in self.spec.terminals:
                self._add_action(state, symbol, SLRAction("shift", target=target))
            elif symbol in self.spec.non_terminals:
                self.goto_table[state][symbol] = target

        for state in self.automaton.states:
            for item in state.items:
                if not self.automaton.is_complete(item):
                    continue
                production = self.automaton.productions[item.production_index]
                if production.lhs == self.automaton.augmented_start:
                    self._add_action(state.id, END_MARKER, SLRAction("accept"))
                    continue
                for terminal in self.follow.get(production.lhs, set()):
                    self._add_action(
                        state.id,
                        terminal,
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
        conflict_type = _conflict_type(existing, action)
        self.conflicts.append(
            SLRConflict(
                state=state,
                terminal=terminal,
                existing=existing,
                new=action,
                conflict_type=conflict_type,
            )
        )


def _conflict_type(existing: SLRAction, new: SLRAction) -> str:
    kinds = {existing.kind, new.kind}
    if "shift" in kinds and "reduce" in kinds:
        return "shift/reduce conflict"
    if existing.kind == "reduce" and new.kind == "reduce":
        return "reduce/reduce conflict"
    return "/".join(sorted(kinds)) + " conflict"


def _append_step(
    steps: List[SLRParseStep],
    verbose: bool,
    stack: List[int],
    lookahead: str,
    action: str,
) -> None:
    if verbose:
        steps.append(SLRParseStep(stack=stack, lookahead=lookahead, action=action))


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
    action: Dict[int, Dict[str, SLRAction]],
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
