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

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Sequence, Set, Tuple

try:  # Permite importar como paquete o como script con sys.path.
    from .yalp_parser import EPSILON, END_MARKER, YalpSpec, format_production
except ImportError:  # pragma: no cover - ruta usada por el CLI de raiz.
    from yalp_parser import EPSILON, END_MARKER, YalpSpec, format_production


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
        self.is_ll1: bool = not self.conflicts

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
