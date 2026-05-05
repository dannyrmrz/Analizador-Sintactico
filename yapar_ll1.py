"""
CLI de avance para preprocesamiento YAPar/YALP + LL(1).

Uso:
    python yapar_ll1.py examples/simple_parser.yalp
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from ll1_analyzer import LL1Analyzer, format_set  # noqa: E402
from yalp_parser import (  # noqa: E402
    YalpParseError,
    YalpSpec,
    format_production,
    parse_yalp_file,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preprocesa un archivo .yalp/.yapar y construye FIRST, FOLLOW y tabla LL(1)."
    )
    parser.add_argument("grammar_file", help="Ruta al archivo .yalp/.yapar")
    args = parser.parse_args(argv)

    grammar_path = Path(args.grammar_file)

    try:
        spec = parse_yalp_file(str(grammar_path))
        analyzer = LL1Analyzer(spec)
    except YalpParseError as exc:
        print("=== YAPar Preprocessing ===")
        print(f"Archivo: {grammar_path}")
        print("")
        print("Resultado:")
        print("No se pudo completar el preprocesamiento.")
        print("")
        print("Errores:")
        print(exc)
        return 1

    print(build_report(grammar_path, spec, analyzer))
    return 0


def build_report(grammar_path: Path, spec: YalpSpec, analyzer: LL1Analyzer) -> str:
    lines: List[str] = [
        "=== YAPar Preprocessing ===",
        f"Archivo: {grammar_path}",
        "",
        "Tokens declarados:",
        _format_ordered(spec.tokens),
        "",
        "Tokens ignorados:",
        _format_ordered(sorted(spec.ignored)),
        "",
        "No terminales:",
        _format_ordered(spec.non_terminals),
        "",
        "Terminales:",
        _format_ordered(sorted(spec.terminals)),
        "",
        "Simbolo inicial:",
        spec.start_symbol,
        "",
        "Producciones:",
    ]

    lines.extend(format_production(prod.lhs, prod.rhs) for prod in spec.productions)

    lines.extend(["", "FIRST:"])
    for non_terminal in spec.non_terminals:
        lines.append(
            f"FIRST({non_terminal}) = {{ {format_set(analyzer.first[non_terminal])} }}"
        )

    lines.extend(["", "FOLLOW:"])
    for non_terminal in spec.non_terminals:
        lines.append(
            f"FOLLOW({non_terminal}) = {{ {format_set(analyzer.follow[non_terminal])} }}"
        )

    lines.extend(["", "Tabla LL(1):"])
    table_lines = _format_table_entries(analyzer)
    lines.extend(table_lines or ["(sin entradas)"])

    lines.extend(["", "Resultado:"])
    if analyzer.conflicts:
        lines.append("Preprocesamiento LL(1) completado con conflictos.")
    else:
        lines.append("Preprocesamiento LL(1) completado.")

    lines.extend(["", "Advertencias/Errores:"])
    if spec.warnings:
        lines.extend(f"- Advertencia: {warning}" for warning in spec.warnings)
    if analyzer.conflicts:
        lines.append("- La gramatica no es LL(1) por conflicto en la tabla.")
        for conflict in analyzer.conflicts:
            lines.extend(
                [
                    f"  No terminal: {conflict.non_terminal}",
                    f"  Terminal de entrada: {conflict.terminal}",
                    f"  Produccion existente: {conflict.existing_text()}",
                    f"  Nueva produccion: {conflict.new_text()}",
                ]
            )
    if not spec.warnings and not analyzer.conflicts:
        lines.append("- OK: tabla LL(1) generada sin conflictos.")

    return "\n".join(lines)


def _format_table_entries(analyzer: LL1Analyzer) -> List[str]:
    lines: List[str] = []
    for non_terminal, terminal, productions in analyzer.table_entries():
        for production in productions:
            suffix = " [conflicto]" if len(productions) > 1 else ""
            lines.append(
                f"M[{non_terminal}, {terminal}] = "
                f"{format_production(non_terminal, production)}{suffix}"
            )
    return lines


def _format_ordered(values: Iterable[str]) -> str:
    items = list(values)
    return ", ".join(items) if items else "(ninguno)"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
