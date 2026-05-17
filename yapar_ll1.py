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
from token_stream import (  # noqa: E402
    LexerOutput,
    LexerTokenInfo,
    TokenConsistencyReport,
    read_lexer_token_info,
    run_lexer,
    validate_tokens,
)
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
    parser.add_argument(
        "-l",
        "--lexer",
        dest="lexer_file",
        help="Ruta a un .yal/.yalex o a un lexer Python generado por YALex",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        help="Archivo de entrada para ejecutar un lexer generado y observar tokens reales",
    )
    parser.add_argument(
        "-o",
        dest="out_parser",
        help="Nombre de salida reservado para el parser generado",
    )
    args = parser.parse_args(argv)

    grammar_path = Path(args.grammar_file)
    lexer_path = Path(args.lexer_file) if args.lexer_file else None
    input_path = Path(args.input_file) if args.input_file else None

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

    lexer_info: Optional[LexerTokenInfo] = None
    lexer_report: Optional[TokenConsistencyReport] = None
    lexer_output: Optional[LexerOutput] = None
    observed_report: Optional[TokenConsistencyReport] = None
    integration_error: Optional[str] = None

    if lexer_path:
        try:
            lexer_info = read_lexer_token_info(str(lexer_path))
            lexer_report = validate_tokens(
                declared_tokens=spec.tokens,
                produced_token_names=lexer_info.produced_token_names,
                ignored_tokens=spec.ignored,
            )
            lexer_report.warnings.extend(lexer_info.warnings)

            if input_path:
                if lexer_path.suffix.lower() in {".yal", ".yalex"}:
                    integration_error = (
                        "--input requiere un lexer Python generado; "
                        "para un .yal primero genere el lexer con yalexgen."
                    )
                else:
                    lexer_output = run_lexer(
                        str(lexer_path),
                        str(input_path),
                        ignored_tokens=spec.ignored,
                    )
                    observed_report = validate_tokens(
                        declared_tokens=spec.tokens,
                        produced_token_names=lexer_output.tokens,
                        ignored_tokens=spec.ignored,
                    )
        except RuntimeError as exc:
            integration_error = str(exc)

    print(
        build_report(
            grammar_path=grammar_path,
            spec=spec,
            analyzer=analyzer,
            lexer_path=lexer_path,
            lexer_info=lexer_info,
            lexer_report=lexer_report,
            input_path=input_path,
            lexer_output=lexer_output,
            observed_report=observed_report,
            out_parser=args.out_parser,
            integration_error=integration_error,
        )
    )

    if integration_error:
        return 1
    if lexer_report and lexer_report.has_errors():
        return 1
    if observed_report and observed_report.has_errors():
        return 1
    if lexer_output and lexer_output.has_errors():
        return 1
    return 0


def build_report(
    grammar_path: Path,
    spec: YalpSpec,
    analyzer: LL1Analyzer,
    lexer_path: Optional[Path] = None,
    lexer_info: Optional[LexerTokenInfo] = None,
    lexer_report: Optional[TokenConsistencyReport] = None,
    input_path: Optional[Path] = None,
    lexer_output: Optional[LexerOutput] = None,
    observed_report: Optional[TokenConsistencyReport] = None,
    out_parser: Optional[str] = None,
    integration_error: Optional[str] = None,
) -> str:
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

    if out_parser:
        lines.extend(
            [
                "",
                "Salida solicitada:",
                f"{out_parser} (pendiente: este avance aun no emite parser generado)",
            ]
        )

    if lexer_path:
        lines.extend(
            _format_lexer_integration(
                lexer_path=lexer_path,
                lexer_info=lexer_info,
                lexer_report=lexer_report,
                input_path=input_path,
                lexer_output=lexer_output,
                observed_report=observed_report,
                integration_error=integration_error,
            )
        )

    lines.extend(["", "Resultado:"])
    if integration_error:
        lines.append("Preprocesamiento completado con error de integracion YALex/YAPar.")
    elif lexer_report and lexer_report.has_errors():
        lines.append("Preprocesamiento completado con errores de tokens YALex/YAPar.")
    elif observed_report and observed_report.has_errors():
        lines.append("Preprocesamiento completado con errores en tokens observados.")
    elif lexer_output and lexer_output.has_errors():
        lines.append("Preprocesamiento completado con errores lexicos en la entrada.")
    elif analyzer.conflicts:
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


def _format_lexer_integration(
    lexer_path: Path,
    lexer_info: Optional[LexerTokenInfo],
    lexer_report: Optional[TokenConsistencyReport],
    input_path: Optional[Path],
    lexer_output: Optional[LexerOutput],
    observed_report: Optional[TokenConsistencyReport],
    integration_error: Optional[str],
) -> List[str]:
    lines: List[str] = ["", "Integracion YALex:"]
    lines.append(f"Lexer: {lexer_path}")

    if integration_error:
        lines.append(f"- Error: {integration_error}")
        return lines

    if lexer_info:
        lines.append("Tokens producidos por YALex:")
        lines.append(_format_ordered(lexer_info.token_names))
        lines.append("Tokens omitidos por YALex:")
        lines.append(_format_ordered(sorted(lexer_info.skipped_token_names)))
        lines.append("Token EOF de YALex:")
        lines.append(lexer_info.eof_token or "(ninguno)")

    if lexer_report:
        lines.append("Validacion de tokens declarados:")
        _append_report_lines(lines, lexer_report)

    if input_path:
        lines.append("Entrada lexica:")
        lines.append(str(input_path))

        if lexer_output:
            observed = [token.type for token in lexer_output.tokens]
            lines.append("Tokens observados:")
            lines.append(_format_ordered(observed))
            if lexer_output.errors:
                lines.append("Errores lexicos:")
                lines.extend(f"- {error}" for error in lexer_output.errors)

        if observed_report:
            lines.append("Validacion de tokens observados:")
            _append_report_lines(lines, observed_report)

    return lines


def _append_report_lines(lines: List[str], report: TokenConsistencyReport) -> None:
    if not report.errors and not report.warnings:
        lines.append("- OK: tokens consistentes.")
        return
    lines.extend(f"- Error: {error}" for error in report.errors)
    lines.extend(f"- Advertencia: {warning}" for warning in report.warnings)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
