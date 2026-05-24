"""
ll1_analyzer.py
===============
Preprocesamiento para el analizador sintactico LL(1).

Calcula:
  - FIRST para cada simbolo relevante.
  - FOLLOW para cada no terminal.
  - Tabla predictiva M[A, a].
  - Conflictos cuando una celda recibe mas de una produccion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

try:  # Permite importar como paquete o como script con sys.path.
    from .semantic_tree import SemanticNode
    from .yalp_parser import EPSILON, END_MARKER, YalpSpec, format_production
    from .token_stream import EOF_TOKEN, Token, TokenStream
except ImportError:  # pragma: no cover - ruta usada por el CLI de raiz.
    from semantic_tree import SemanticNode
    from yalp_parser import EPSILON, END_MARKER, YalpSpec, format_production
    from token_stream import EOF_TOKEN, Token, TokenStream


@dataclass
class LL1Conflict:
    """Una insercion conflictiva en la tabla LL(1)."""

    non_terminal: str
    terminal: str
    existing: List[str]
    new: List[str]

    def existing_text(self) -> str:
        return format_production(self.non_terminal, self.existing)

    def new_text(self) -> str:
        return format_production(self.non_terminal, self.new)


@dataclass
class LL1ParseStep:
    """Un paso del parser predictivo LL(1)."""

    stack: List[str]
    lookahead: str
    action: str


@dataclass
class LL1ParseResult:
    """Resultado de ejecutar el parser LL(1)."""

    accepted: bool
    steps: List[LL1ParseStep] = field(default_factory=list)
    tree: Optional[SemanticNode] = None
    error: Optional[str] = None
    token: Optional[Token] = None
    expected: Set[str] = field(default_factory=set)


class LL1Analyzer:
    """
    Preprocesador LL(1): calcula FIRST, FOLLOW y tabla de analisis.

    Uso:
        spec = parse_yalp_file("grammar.yalp")
        analyzer = LL1Analyzer(spec)
        print(analyzer.report_first_follow())
        print(analyzer.report_table())
    """

    def __init__(self, spec: YalpSpec) -> None:
        self.spec = spec
        self.grammar = spec.grammar
        self.non_terminals: List[str] = spec.non_terminals
        self.terminals: Set[str] = set(spec.terminals)
        self.start_symbol: str = spec.start_symbol

        self.first: Dict[str, Set[str]] = self._compute_first()
        self.follow: Dict[str, Set[str]] = self._compute_follow()
        self.conflicts: List[LL1Conflict] = []
        self.table: Dict[str, Dict[str, List[List[str]]]] = self._build_table()
        self.left_recursive_non_terminals: Set[str] = self.detect_left_recursion()
        self.is_ll1: bool = not self.conflicts and not self.left_recursive_non_terminals

    def _compute_first(self) -> Dict[str, Set[str]]:
        """
        Calcula FIRST por punto fijo.

        Reglas principales:
        - Si X es terminal, FIRST(X) = {X}.
        - Si X es epsilon, FIRST(X) = {epsilon}.
        - Para A -> X1 X2 ... Xn, se agregan FIRST(Xi) sin epsilon
          mientras los simbolos anteriores puedan derivar epsilon.
        """
        first: Dict[str, Set[str]] = {}

        for nt in self.non_terminals:
            first[nt] = set()
        for terminal in self.terminals:
            first[terminal] = {terminal}
        first[EPSILON] = {EPSILON}
        first[END_MARKER] = {END_MARKER}

        changed = True
        while changed:
            changed = False
            for head, productions in self.grammar.items():
                for production in productions:
                    before = len(first[head])
                    first[head].update(self.first_of_string_with(first, production))
                    if len(first[head]) != before:
                        changed = True

        return first

    def first_of_string(self, symbols: Sequence[str]) -> Set[str]:
        """Calcula FIRST de una secuencia usando los FIRST ya calculados."""
        return self.first_of_string_with(self.first, symbols)

    def first_of_string_with(
        self,
        first: Dict[str, Set[str]],
        symbols: Sequence[str],
    ) -> Set[str]:
        """Calcula FIRST(alpha) con una tabla FIRST parcial o final."""
        if not symbols:
            return {EPSILON}

        result: Set[str] = set()
        all_can_be_epsilon = True

        for symbol in symbols:
            symbol_first = first.get(symbol, {symbol})
            result.update(symbol_first - {EPSILON})
            if EPSILON not in symbol_first:
                all_can_be_epsilon = False
                break

        if all_can_be_epsilon:
            result.add(EPSILON)
        return result

    def _compute_follow(self) -> Dict[str, Set[str]]:
        """
        Calcula FOLLOW por punto fijo.

        - FOLLOW(S) inicia con $.
        - En A -> alpha B beta, FIRST(beta) sin epsilon entra en FOLLOW(B).
        - Si beta deriva epsilon o B esta al final, FOLLOW(A) entra en FOLLOW(B).
        """
        follow: Dict[str, Set[str]] = {nt: set() for nt in self.non_terminals}
        follow[self.start_symbol].add(END_MARKER)

        changed = True
        while changed:
            changed = False
            for head, productions in self.grammar.items():
                for production in productions:
                    if production == [EPSILON]:
                        continue
                    for index, symbol in enumerate(production):
                        if symbol not in follow:
                            continue

                        beta = production[index + 1 :]
                        first_beta = self.first_of_string(beta)

                        before = len(follow[symbol])
                        follow[symbol].update(first_beta - {EPSILON})
                        if EPSILON in first_beta:
                            follow[symbol].update(follow[head])
                        if len(follow[symbol]) != before:
                            changed = True

        return follow

    def _build_table(self) -> Dict[str, Dict[str, List[List[str]]]]:
        """
        Construye la tabla LL(1).

        Para A -> alpha:
        - Cada terminal de FIRST(alpha) sin epsilon recibe A -> alpha.
        - Si epsilon esta en FIRST(alpha), cada simbolo de FOLLOW(A) recibe
          A -> alpha.
        """
        table: Dict[str, Dict[str, List[List[str]]]] = {
            nt: {} for nt in self.non_terminals
        }

        for head, productions in self.grammar.items():
            for production in productions:
                first_alpha = self.first_of_string(production)

                for terminal in first_alpha - {EPSILON}:
                    self._add_table_entry(table, head, terminal, production)

                if EPSILON in first_alpha:
                    for terminal in self.follow[head]:
                        self._add_table_entry(table, head, terminal, production)

        return table

    def _add_table_entry(
        self,
        table: Dict[str, Dict[str, List[List[str]]]],
        non_terminal: str,
        terminal: str,
        production: Sequence[str],
    ) -> None:
        row = table.setdefault(non_terminal, {})
        cell = row.setdefault(terminal, [])
        new_production = list(production)

        if new_production in cell:
            return

        if cell:
            self.conflicts.append(
                LL1Conflict(
                    non_terminal=non_terminal,
                    terminal=terminal,
                    existing=list(cell[0]),
                    new=new_production,
                )
            )

        cell.append(new_production)

    def table_entries(self) -> Iterator[Tuple[str, str, List[List[str]]]]:
        """Itera las celdas no vacias de la tabla, en orden estable."""
        for non_terminal in self.non_terminals:
            row = self.table.get(non_terminal, {})
            for terminal in sorted(row):
                yield non_terminal, terminal, row[terminal]

    def detect_left_recursion(self) -> Set[str]:
        """
        Detecta recursion izquierda directa o indirecta usando los primeros
        no terminales alcanzables al inicio de cada produccion.
        """
        edges: Dict[str, Set[str]] = {nt: set() for nt in self.non_terminals}
        for head, productions in self.grammar.items():
            for production in productions:
                if production == [EPSILON]:
                    continue
                for symbol in production:
                    if symbol in edges:
                        edges[head].add(symbol)
                        if EPSILON in self.first.get(symbol, set()):
                            continue
                    break

        recursive: Set[str] = set()
        for start in self.non_terminals:
            stack = list(edges[start])
            seen: Set[str] = set()
            while stack:
                current = stack.pop()
                if current == start:
                    recursive.add(start)
                    break
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(edges.get(current, set()) - seen)
        return recursive

    def parse(
        self,
        tokens: Sequence[Token] | TokenStream,
        verbose: bool = False,
    ) -> LL1ParseResult:
        """
        Ejecuta el parser predictivo LL(1) usando la tabla generada.

        Si la gramatica tiene conflictos LL(1), se reporta incompatibilidad
        sin modificar la gramatica. SLR(1) puede probarse por separado.
        """
        if self.conflicts:
            return LL1ParseResult(
                accepted=False,
                error="La gramatica no es compatible con LL(1); hay conflictos en la tabla.",
            )
        if self.left_recursive_non_terminals:
            return LL1ParseResult(
                accepted=False,
                error=(
                    "La gramatica tiene recursion izquierda y no es compatible con LL(1): "
                    + ", ".join(sorted(self.left_recursive_non_terminals))
                ),
            )

        stream = tokens if isinstance(tokens, TokenStream) else TokenStream(list(tokens))
        root = SemanticNode(self.start_symbol)
        stack: List[Tuple[str, Optional[SemanticNode]]] = [
            (END_MARKER, None),
            (self.start_symbol, root),
        ]
        steps: List[LL1ParseStep] = []

        while stack:
            top, node = stack.pop()
            lookahead = stream.current
            lookahead_type = _normalize_eof_type(lookahead.type)
            shown_stack = [symbol for symbol, _ in stack] + [top]

            if top == EPSILON:
                _append_step(steps, verbose, shown_stack, lookahead_type, "epsilon")
                continue

            if top == END_MARKER:
                if lookahead_type == END_MARKER:
                    _append_step(steps, verbose, shown_stack, lookahead_type, "accept")
                    return LL1ParseResult(accepted=True, steps=steps, tree=root)
                return LL1ParseResult(
                    accepted=False,
                    steps=steps,
                    tree=root,
                    error=_unexpected_token_message(
                        lookahead,
                        {END_MARKER},
                        "EOF esperado",
                    ),
                    token=lookahead,
                    expected={END_MARKER},
                )

            if self.spec.is_terminal(top):
                if top == lookahead_type:
                    if node is not None:
                        node.lexeme = lookahead.lexeme
                        node.line = None if lookahead.line < 0 else lookahead.line
                        node.column = None if lookahead.col < 0 else lookahead.col
                    stream.consume()
                    _append_step(
                        steps,
                        verbose,
                        shown_stack,
                        lookahead_type,
                        f"match {top}",
                    )
                    continue
                return LL1ParseResult(
                    accepted=False,
                    steps=steps,
                    tree=root,
                    error=_unexpected_token_message(
                        lookahead,
                        {top},
                        f"Terminal esperado: {top}",
                    ),
                    token=lookahead,
                    expected={top},
                )

            row = self.table.get(top, {})
            productions = row.get(lookahead_type)
            if not productions:
                expected = set(row)
                return LL1ParseResult(
                    accepted=False,
                    steps=steps,
                    tree=root,
                    error=_unexpected_token_message(
                        lookahead,
                        expected,
                        f"No hay produccion para M[{top}, {lookahead_type}]",
                    ),
                    token=lookahead,
                    expected=expected,
                )
            if len(productions) > 1:
                return LL1ParseResult(
                    accepted=False,
                    steps=steps,
                    tree=root,
                    error=f"Conflicto LL(1) en M[{top}, {lookahead_type}].",
                    token=lookahead,
                    expected={lookahead_type},
                )

            production = productions[0]
            _append_step(
                steps,
                verbose,
                shown_stack,
                lookahead_type,
                format_production(top, production),
            )
            child_nodes: List[SemanticNode] = []
            if production == [EPSILON]:
                child_nodes.append(SemanticNode.epsilon())
            else:
                child_nodes.extend(SemanticNode(symbol) for symbol in production)
            if node is not None:
                node.children.extend(child_nodes)
            for symbol, child in reversed(list(zip(production, child_nodes))):
                if symbol != EPSILON:
                    stack.append((symbol, child))

        current = stream.current if not stream.at_end else EOF_TOKEN
        return LL1ParseResult(
            accepted=False,
            steps=steps,
            tree=root,
            error=_unexpected_token_message(current, {END_MARKER}, "EOF inesperado"),
            token=current,
            expected={END_MARKER},
        )

    def report_first_follow(self) -> str:
        lines = ["FIRST:"]
        for nt in self.non_terminals:
            lines.append(f"FIRST({nt}) = {{ {format_set(self.first[nt])} }}")

        lines.append("")
        lines.append("FOLLOW:")
        for nt in self.non_terminals:
            lines.append(f"FOLLOW({nt}) = {{ {format_set(self.follow[nt])} }}")

        return "\n".join(lines)

    def report_table(self) -> str:
        lines = ["Tabla LL(1):"]
        for non_terminal, terminal, productions in self.table_entries():
            for production in productions:
                marker = " [conflicto]" if len(productions) > 1 else ""
                lines.append(
                    f"M[{non_terminal}, {terminal}] = "
                    f"{format_production(non_terminal, production)}{marker}"
                )

        if len(lines) == 1:
            lines.append("(tabla vacia)")

        lines.append("")
        lines.append(self.report_conflicts())
        return "\n".join(lines)

    def report_conflicts(self) -> str:
        if not self.conflicts:
            if self.left_recursive_non_terminals:
                return (
                    "La tabla LL(1) no tuvo celdas conflictivas, pero se detecto "
                    "recursion izquierda en: "
                    + ", ".join(sorted(self.left_recursive_non_terminals))
                )
            return "La tabla LL(1) se genero sin conflictos."

        lines = [
            "La gramatica no es LL(1) por conflicto en la tabla.",
            "Conflictos LL(1):",
        ]
        for conflict in self.conflicts:
            lines.extend(
                [
                    f"- No terminal: {conflict.non_terminal}",
                    f"  Terminal de entrada: {conflict.terminal}",
                    f"  Produccion existente: {conflict.existing_text()}",
                    f"  Nueva produccion: {conflict.new_text()}",
                ]
            )
        return "\n".join(lines)


def format_set(values: Iterable[str]) -> str:
    return ", ".join(sorted(values)) if values else ""


def _append_step(
    steps: List[LL1ParseStep],
    verbose: bool,
    stack: List[str],
    lookahead: str,
    action: str,
) -> None:
    if verbose:
        steps.append(LL1ParseStep(stack=stack, lookahead=lookahead, action=action))


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
