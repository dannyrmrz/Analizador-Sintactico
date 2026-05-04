"""
ll1_analyzer.py
===============
Pre-procesamiento para el analizador sintáctico LL(1).

Calcula:
  - Conjuntos FIRST para cada símbolo de la gramática
  - Conjuntos FOLLOW para cada no-terminal
  - Tabla de análisis predictivo M[A, a]
  - Detección de conflictos (gramática no-LL(1))
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .yalp_parser import EPSILON, END_MARKER, YalpSpec


class LL1Analyzer:
    """
    Pre-procesador LL(1): calcula FIRST, FOLLOW y tabla de análisis.

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
        self.terminals: Set[str] = spec.terminals
        self.start_symbol: str = spec.start_symbol

        self.first: Dict[str, Set[str]] = self._compute_first()
        self.follow: Dict[str, Set[str]] = self._compute_follow()
        self.table: Dict[str, Dict[str, List[List[str]]]] = self._build_table()
        self.conflicts: List[Tuple[str, str, List[List[str]]]] = self._find_conflicts()
        self.is_ll1: bool = len(self.conflicts) == 0

    # ── FIRST ────────────────────────────────────────────────────────────────

    def _compute_first(self) -> Dict[str, Set[str]]:
        """
        Calcula FIRST para todos los símbolos de la gramática.

        Reglas:
          - Si X es terminal: FIRST(X) = {X}
          - Si X -> ε:        ε ∈ FIRST(X)
          - Si X -> Y1 Y2…Yk: agrega FIRST(Y1)-{ε};
                               si ε ∈ FIRST(Y1) agrega FIRST(Y2)-{ε}, etc.
                               si todos derivan ε, agrega ε a FIRST(X)
        """
        first: Dict[str, Set[str]] = {}

        for nt in self.non_terminals:
            first[nt] = set()
        for t in self.terminals:
            first[t] = {t}
        first[EPSILON] = {EPSILON}
        first[END_MARKER] = {END_MARKER}

        changed = True
        while changed:
            changed = False
            for head, productions in self.grammar.items():
                for prod in productions:
                    if prod == [EPSILON]:
                        if EPSILON not in first[head]:
                            first[head].add(EPSILON)
                            changed = True
                        continue

                    all_derive_epsilon = True
                    for symbol in prod:
                        sym_first = first.get(symbol, {symbol})
                        before = len(first[head])
                        first[head] |= (sym_first - {EPSILON})
                        if len(first[head]) > before:
                            changed = True
                        if EPSILON not in sym_first:
                            all_derive_epsilon = False
                            break

                    if all_derive_epsilon:
                        if EPSILON not in first[head]:
                            first[head].add(EPSILON)
                            changed = True

        return first

    def first_of_string(self, symbols: List[str]) -> Set[str]:
        """Calcula FIRST de una secuencia de símbolos."""
        result: Set[str] = set()
        for sym in symbols:
            sym_first = self.first.get(sym, {sym})
            result |= (sym_first - {EPSILON})
            if EPSILON not in sym_first:
                break
        else:
            result.add(EPSILON)
        return result

    # ── FOLLOW ───────────────────────────────────────────────────────────────

    def _compute_follow(self) -> Dict[str, Set[str]]:
        """
        Calcula FOLLOW para todos los no-terminales.

        Reglas:
          - $ ∈ FOLLOW(S) donde S es el símbolo inicial
          - Si A -> αBβ:              FIRST(β)-{ε} ⊆ FOLLOW(B)
          - Si A -> αB o
            A -> αBβ con ε∈FIRST(β): FOLLOW(A) ⊆ FOLLOW(B)
        """
        follow: Dict[str, Set[str]] = {nt: set() for nt in self.non_terminals}
        follow[self.start_symbol].add(END_MARKER)

        changed = True
        while changed:
            changed = False
            for head, productions in self.grammar.items():
                for prod in productions:
                    if prod == [EPSILON]:
                        continue
                    for i, symbol in enumerate(prod):
                        if symbol not in self.non_terminals:
                            continue
                        beta = prod[i + 1:]
                        if beta:
                            first_beta = self.first_of_string(beta)
                            before = len(follow[symbol])
                            follow[symbol] |= (first_beta - {EPSILON})
                            if len(follow[symbol]) > before:
                                changed = True
                            if EPSILON in first_beta:
                                before = len(follow[symbol])
                                follow[symbol] |= follow[head]
                                if len(follow[symbol]) > before:
                                    changed = True
                        else:
                            before = len(follow[symbol])
                            follow[symbol] |= follow[head]
                            if len(follow[symbol]) > before:
                                changed = True

        return follow

    # ── Tabla de análisis ────────────────────────────────────────────────────

    def _build_table(self) -> Dict[str, Dict[str, List[List[str]]]]:
        """
        Construye la tabla de análisis predictivo M[A, a].

        Para cada producción A -> α:
          - Para cada a ∈ FIRST(α)-{ε}: agrega A->α en M[A, a]
          - Si ε ∈ FIRST(α): para cada b ∈ FOLLOW(A), agrega A->α en M[A, b]
        """
        table: Dict[str, Dict[str, List[List[str]]]] = {
            nt: {} for nt in self.non_terminals
        }

        for head, productions in self.grammar.items():
            for prod in productions:
                first_alpha = self.first_of_string(prod)

                for terminal in first_alpha - {EPSILON}:
                    table[head].setdefault(terminal, []).append(prod)

                if EPSILON in first_alpha:
                    for terminal in self.follow[head]:
                        table[head].setdefault(terminal, []).append(prod)

        return table

    def _find_conflicts(self) -> List[Tuple[str, str, List[List[str]]]]:
        """Retorna las celdas con más de una producción (conflictos LL(1))."""
        return [
            (nt, t, prods)
            for nt, row in self.table.items()
            for t, prods in row.items()
            if len(prods) > 1
        ]

    # ── Reportes ──────────────────────────────────────────────────────────────

    def report_first_follow(self) -> str:
        lines = ["=" * 55, "  CONJUNTOS FIRST", "=" * 55]
        for nt in self.non_terminals:
            items = ", ".join(sorted(self.first[nt]))
            lines.append(f"  FIRST({nt}) = {{ {items} }}")
        lines += ["", "=" * 55, "  CONJUNTOS FOLLOW", "=" * 55]
        for nt in self.non_terminals:
            items = ", ".join(sorted(self.follow[nt]))
            lines.append(f"  FOLLOW({nt}) = {{ {items} }}")
        return "\n".join(lines)

    def report_table(self) -> str:
        all_terms = sorted(self.terminals | {END_MARKER})
        col_w = 22
        sep = "=" * (8 + col_w * len(all_terms))
        lines = [sep, "  TABLA DE ANALISIS SINTACTICO LL(1)", sep]
        header = f"{'NT':<8}" + "".join(f"{t:^{col_w}}" for t in all_terms)
        lines += [header, "-" * len(header)]
        for nt in self.non_terminals:
            row = f"{nt:<8}"
            for t in all_terms:
                prods = self.table[nt].get(t, [])
                if prods:
                    rhs = " ".join(prods[0]) if prods[0] != [EPSILON] else EPSILON
                    cell = f"{nt}->{rhs}" + (" [!]" if len(prods) > 1 else "")
                else:
                    cell = ""
                row += f"{cell:^{col_w}}"
            lines.append(row)

        lines.append("")
        if self.conflicts:
            lines.append(f"[!] NO es LL(1): {len(self.conflicts)} conflicto(s)")
            for nt, t, prods in self.conflicts:
                lines.append(f"    M[{nt}, {t}] tiene {len(prods)} producciones")
        else:
            lines.append("[OK] Gramatica es LL(1)")
        return "\n".join(lines)
