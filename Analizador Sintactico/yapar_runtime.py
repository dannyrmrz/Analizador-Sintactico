"""
yapar_runtime.py
================
Funciones compartidas por el CLI `yapar.py` y por parsers generados.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .lalr_parser import LALRParser
    from .ll1_analyzer import LL1Analyzer
    from .lr0_automaton import LR0Automaton
    from .semantic_tree import SemanticNode, write_tree_dot, write_tree_json
    from .slr_parser import SLRParser
    from .token_stream import (
        LexerOutput,
        read_lexer_token_info,
        run_lexer,
        token_stream_from_lexer_output,
        validate_tokens,
    )
    from .yalp_parser import YalpParseError, parse_yalp_file
except ImportError:  # pragma: no cover
    from lalr_parser import LALRParser
    from ll1_analyzer import LL1Analyzer
    from lr0_automaton import LR0Automaton
    from semantic_tree import SemanticNode, write_tree_dot, write_tree_json
    from slr_parser import SLRParser
    from token_stream import (
        LexerOutput,
        read_lexer_token_info,
        run_lexer,
        token_stream_from_lexer_output,
        validate_tokens,
    )
    from yalp_parser import YalpParseError, parse_yalp_file


@dataclass
class RuntimeResult:
    ok: bool
    message: str
    tree: Optional[SemanticNode] = None
    method: str = ""


def run_yapar(
    grammar_file: str,
    lexer_file: Optional[str] = None,
    input_file: Optional[str] = None,
    method: str = "slr",
    dot_file: Optional[str] = None,
    json_file: Optional[str] = None,
    tree_dot_file: Optional[str] = None,
    tree_json_file: Optional[str] = None,
    show_tree: bool = False,
    verbose: bool = False,
    recover: bool = False,
) -> RuntimeResult:
    try:
        spec = parse_yalp_file(grammar_file)
    except YalpParseError as exc:
        return RuntimeResult(False, str(exc), method=method)

    lines = [
        "=== YAPar ===",
        f"Grammar: {grammar_file}",
        f"Method: {method}",
        f"Start: {spec.start_symbol}",
        f"Tokens: {', '.join(spec.tokens)}",
    ]

    lexer_script = None
    lexer_output: Optional[LexerOutput] = None
    if lexer_file:
        try:
            lexer_info = read_lexer_token_info(lexer_file)
            report = validate_tokens(
                spec.tokens,
                lexer_info.produced_token_names,
                spec.ignored,
            )
        except RuntimeError as exc:
            return RuntimeResult(False, str(exc), method=method)

        lines.append("Lexer tokens: " + ", ".join(sorted(lexer_info.produced_token_names)))
        for warning in report.warnings:
            lines.append("Warning: " + warning)
        if report.errors:
            lines.extend("Error: " + error for error in report.errors)
            return RuntimeResult(False, "\n".join(lines), method=method)

        if input_file:
            try:
                lexer_script = ensure_lexer_script(lexer_file)
                lexer_output = run_lexer(lexer_script, input_file, ignored_tokens=spec.ignored)
            except RuntimeError as exc:
                return RuntimeResult(False, str(exc), method=method)
            if lexer_output.errors:
                lines.extend("Lexical error: " + error for error in lexer_output.errors)
                return RuntimeResult(False, "\n".join(lines), method=method)
            observed_report = validate_tokens(
                spec.tokens,
                lexer_output.tokens,
                spec.ignored,
                warn_missing=False,
            )
            for warning in observed_report.warnings:
                lines.append("Warning: " + warning)
            if observed_report.errors:
                lines.extend("Error: " + error for error in observed_report.errors)
                return RuntimeResult(False, "\n".join(lines), method=method)

    if method == "ll1":
        analyzer = LL1Analyzer(spec)
        lines.append(analyzer.report_conflicts())
        if input_file:
            if lexer_output is None:
                return RuntimeResult(False, "Para parsear entrada con LL(1) se requiere -l y --input.", method=method)
            result = analyzer.parse(
                token_stream_from_lexer_output(lexer_output),
                verbose=verbose,
                recover=recover,
            )
            lines.extend(_format_ll1_steps(result.steps))
            lines.append("Accepted" if result.accepted else "Rejected")
            _append_tree_outputs(
                lines,
                result.tree,
                accepted=result.accepted,
                tree_dot_file=tree_dot_file,
                tree_json_file=tree_json_file,
                show_tree=show_tree,
            )
            for error in getattr(result, "errors", []):
                lines.append("Recovered error: " + error)
            if result.error:
                lines.append("Error: " + result.error)
            return RuntimeResult(result.accepted, "\n".join(lines), tree=result.tree, method=method)
        return RuntimeResult(analyzer.is_ll1, "\n".join(lines), method=method)

    if method == "lr0":
        automaton = LR0Automaton.build(spec)
        if dot_file:
            automaton.write_dot(dot_file)
            lines.append(f"LR(0) DOT: {dot_file}")
        if json_file:
            Path(json_file).write_text(
                json.dumps(automaton.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            lines.append(f"LR(0) JSON: {json_file}")
        lines.append(f"LR(0) states: {len(automaton.states)}")
        return RuntimeResult(True, "\n".join(lines), method=method)

    if method == "slr":
        parser = SLRParser(spec)
        if dot_file:
            parser.automaton.write_dot(dot_file)
            lines.append(f"LR(0) DOT: {dot_file}")
        if json_file:
            Path(json_file).write_text(
                json.dumps(
                    {
                        "lr0": parser.automaton.to_dict(),
                        "slr": parser.to_dict(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            lines.append(f"SLR JSON: {json_file}")
        if parser.conflicts:
            lines.append("La gramatica no es SLR(1).")
            lines.extend(
                "Conflict: " + conflict.text(parser.automaton.productions)
                for conflict in parser.conflicts
            )
            return RuntimeResult(False, "\n".join(lines), method=method)
        lines.append(f"SLR states: {len(parser.automaton.states)}")
        lines.append("SLR table: OK")
        if input_file:
            if lexer_output is None:
                return RuntimeResult(False, "Para parsear entrada con SLR(1) se requiere -l y --input.", method=method)
            result = parser.parse(
                token_stream_from_lexer_output(lexer_output),
                verbose=verbose,
                recover=recover,
            )
            lines.extend(_format_slr_steps(result.steps))
            lines.append("Accepted" if result.accepted else "Rejected")
            _append_tree_outputs(
                lines,
                result.tree,
                accepted=result.accepted,
                tree_dot_file=tree_dot_file,
                tree_json_file=tree_json_file,
                show_tree=show_tree,
            )
            for error in getattr(result, "errors", []):
                lines.append("Recovered error: " + error)
            if result.error:
                lines.append("Error: " + result.error)
            return RuntimeResult(result.accepted, "\n".join(lines), tree=result.tree, method=method)
        return RuntimeResult(True, "\n".join(lines), method=method)

    if method == "lalr":
        parser = LALRParser(spec)
        if dot_file:
            parser.write_dot(dot_file)
            lines.append(f"LALR DOT: {dot_file}")
        if json_file:
            Path(json_file).write_text(
                json.dumps(
                    {
                        "lalr": parser.to_dict(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            lines.append(f"LALR JSON: {json_file}")
        if parser.conflicts:
            lines.append("La gramatica no es LALR(1).")
            lines.extend(
                "Conflict: " + conflict.text(parser.productions)
                for conflict in parser.conflicts
            )
            return RuntimeResult(False, "\n".join(lines), method=method)
        lines.append(f"Canonical LR(1) states: {len(parser.lr1_states)}")
        lines.append(f"LALR states: {len(parser.states)}")
        lines.append("LALR table: OK")
        if input_file:
            if lexer_output is None:
                return RuntimeResult(False, "Para parsear entrada con LALR(1) se requiere -l y --input.", method=method)
            result = parser.parse(
                token_stream_from_lexer_output(lexer_output),
                verbose=verbose,
                recover=recover,
            )
            lines.extend(_format_lalr_steps(result.steps))
            lines.append("Accepted" if result.accepted else "Rejected")
            _append_tree_outputs(
                lines,
                result.tree,
                accepted=result.accepted,
                tree_dot_file=tree_dot_file,
                tree_json_file=tree_json_file,
                show_tree=show_tree,
            )
            for error in result.errors:
                lines.append("Recovered error: " + error)
            if result.error:
                lines.append("Error: " + result.error)
            return RuntimeResult(result.accepted, "\n".join(lines), tree=result.tree, method=method)
        return RuntimeResult(True, "\n".join(lines), method=method)

    return RuntimeResult(False, f"Metodo desconocido: {method}", method=method)


def ensure_lexer_script(lexer_file: str) -> str:
    path = Path(lexer_file).resolve()
    if path.suffix.lower() not in {".yal", ".yalex"}:
        return str(path)

    root = Path(__file__).resolve().parents[1]
    lex_dir = root / "Analizador Lexico"
    out_dir = root / "generated"
    out_dir.mkdir(exist_ok=True)
    out_script = out_dir / (path.stem + "_lexer.py")
    cmd = [
        sys.executable,
        str(lex_dir / "yalexgen"),
        str(path),
        "-o",
        str(out_script),
        "--dot",
        str(out_dir / (path.stem + "_regex_tree.dot")),
        "--no-png",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(lex_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError("No se pudo generar lexer desde YALex: " + detail)
    return str(out_script)


def emit_parser_runner(
    output_file: str,
    grammar_file: str,
    lexer_file: str,
    method: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    script = f'''#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path({str(root)!r})
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from yapar_runtime import run_yapar

if len(sys.argv) < 2:
    print(f"Usage: {{sys.argv[0]}} <input.txt>")
    raise SystemExit(1)

result = run_yapar(
    grammar_file={str(Path(grammar_file).resolve())!r},
    lexer_file={str(Path(lexer_file).resolve())!r},
    input_file=sys.argv[1],
    method={method!r},
    show_tree="--tree" in sys.argv[2:],
)
print(result.message)
raise SystemExit(0 if result.ok else 1)
'''
    output.write_text(script, encoding="utf-8", newline="\n")


def _format_ll1_steps(steps: object) -> list[str]:
    lines: list[str] = []
    for step in steps:
        lines.append(
            f"LL1 step stack={step.stack} lookahead={step.lookahead} action={step.action}"
        )
    return lines


def _format_slr_steps(steps: object) -> list[str]:
    lines: list[str] = []
    for step in steps:
        lines.append(
            f"SLR step stack={step.stack} lookahead={step.lookahead} action={step.action}"
        )
    return lines


def _format_lalr_steps(steps: object) -> list[str]:
    lines: list[str] = []
    for step in steps:
        lines.append(
            f"LALR step stack={step.stack} lookahead={step.lookahead} action={step.action}"
        )
    return lines


def _append_tree_outputs(
    lines: list[str],
    tree: Optional[SemanticNode],
    accepted: bool,
    tree_dot_file: Optional[str],
    tree_json_file: Optional[str],
    show_tree: bool,
) -> None:
    if not accepted or tree is None:
        if tree_dot_file or tree_json_file or show_tree:
            lines.append("Semantic tree: unavailable because parsing was not accepted.")
        return

    if tree_dot_file:
        write_tree_dot(tree, tree_dot_file)
        lines.append(f"Semantic tree DOT: {tree_dot_file}")
    if tree_json_file:
        write_tree_json(tree, tree_json_file)
        lines.append(f"Semantic tree JSON: {tree_json_file}")
    if show_tree:
        lines.append("Semantic tree:")
        lines.append(tree.pretty())
