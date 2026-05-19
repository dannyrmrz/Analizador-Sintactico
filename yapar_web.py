#!/usr/bin/env python3
"""Servidor web local para trabajar con YAPar desde el navegador."""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from lalr_parser import LALRParser  # noqa: E402
from ll1_analyzer import LL1Analyzer  # noqa: E402
from lr0_automaton import LR0Automaton  # noqa: E402
from slr_parser import SLRParser  # noqa: E402
from token_stream import read_lexer_token_info, run_lexer, validate_tokens  # noqa: E402
from yalp_parser import YalpParseError, format_production, parse_yalp  # noqa: E402
from yapar_runtime import ensure_lexer_script, run_yapar  # noqa: E402


DEMO_CONFIGS = [
    {
        "id": "calculator-slr",
        "title": "Calculadora SLR",
        "description": "Expresiones aritmeticas con precedencia y parentesis.",
        "method": "slr",
        "grammar": "examples/calculator_parser.yalp",
        "lexer": "Analizador Lexico/examples/calculator.yal",
        "input": "examples/calculator_input_ok.txt",
    },
    {
        "id": "calculator-ll1",
        "title": "Calculadora LL(1)",
        "description": "La misma gramatica transformada para parser predictivo.",
        "method": "ll1",
        "grammar": "examples/calculator_parser.yalp",
        "lexer": "Analizador Lexico/examples/calculator.yal",
        "input": "examples/calculator_input_ok.txt",
    },
    {
        "id": "left-recursive-slr",
        "title": "Recursion izquierda SLR",
        "description": "No es LL(1), pero SLR la acepta.",
        "method": "slr",
        "grammar": "examples/slr_left_recursive.yalp",
        "lexer": "examples/number_plus.yal",
        "input": "examples/number_plus_input_ok.txt",
    },
    {
        "id": "lalr-not-slr",
        "title": "LALR que no es SLR",
        "description": "Asignaciones clasicas LR(1)/LALR(1).",
        "method": "lalr",
        "grammar": "examples/lalr_not_slr.yalp",
        "lexer": "examples/id_star_equal.yal",
        "input": "examples/lalr_assignment_input_ok.txt",
    },
    {
        "id": "syntax-error",
        "title": "Error sintactico",
        "description": "Entrada invalida para revisar mensajes y recuperacion.",
        "method": "slr",
        "grammar": "examples/calculator_parser.yalp",
        "lexer": "Analizador Lexico/examples/calculator.yal",
        "input": "examples/calculator_input_error.txt",
    },
]


class YaparWebHandler(BaseHTTPRequestHandler):
    server_version = "YAParWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/examples":
            self._send_json({"examples": _available_examples()})
            return
        if parsed.path == "/api/read":
            self._handle_read(parsed.query)
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "root": str(ROOT)})
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self._send_json({"ok": False, "error": "Ruta no encontrada."}, status=404)
            return

        try:
            payload = self._read_json_body()
            result = analyze_payload(payload)
            self._send_json(result)
        except Exception as exc:  # pragma: no cover - defensa para la UI.
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=4),
                },
                status=500,
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[YAPar Web] " + (fmt % args) + "\n")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _handle_read(self, query: str) -> None:
        params = parse_qs(query)
        requested = params.get("path", [""])[0]
        if not requested:
            self._send_json({"ok": False, "error": "Falta path."}, status=400)
            return
        try:
            path = _safe_project_path(unquote(requested))
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self._send_json({"ok": True, "path": _relative(path), "text": text})

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        try:
            static_path = (WEB_DIR / path.lstrip("/")).resolve()
            if not static_path.is_file() or not _is_inside(static_path, WEB_DIR):
                self._send_json({"ok": False, "error": "Archivo no encontrado."}, status=404)
                return
            content = static_path.read_bytes()
        except OSError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        content_type = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
        if static_path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif static_path.suffix in {".html", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def analyze_payload(payload: dict[str, Any]) -> dict[str, Any]:
    method = str(payload.get("method") or "slr").lower()
    if method not in {"ll1", "lr0", "slr", "lalr"}:
        return {"ok": False, "error": f"Metodo desconocido: {method}"}

    grammar_text = str(payload.get("grammar") or "")
    lexer_text = str(payload.get("lexer") or "")
    input_text = str(payload.get("input") or "")
    lexer_name = str(payload.get("lexerName") or "lexer.yal")
    verbose = bool(payload.get("verbose"))
    recover = bool(payload.get("recover"))

    run_dir = _new_run_dir()
    grammar_file = run_dir / "grammar.yalp"
    input_file = run_dir / "input.txt"
    dot_file = run_dir / f"{method}_automaton.dot"
    json_file = run_dir / f"{method}_structures.json"
    grammar_file.write_text(grammar_text, encoding="utf-8", newline="\n")
    input_file.write_text(input_text, encoding="utf-8", newline="\n")

    response: dict[str, Any] = {
        "ok": True,
        "method": method,
        "run": {"directory": _relative(run_dir)},
        "warnings": [],
        "errors": [],
    }

    try:
        spec = parse_yalp(grammar_text, filename="editor.yalp")
    except YalpParseError as exc:
        response.update({"ok": False, "error": str(exc), "errors": [str(exc)]})
        return response

    response["grammar"] = _spec_to_dict(spec)
    response["warnings"].extend(spec.warnings)

    lexer_file: Optional[Path] = None
    lexer_output = None
    lexer_block: dict[str, Any] = {"enabled": bool(lexer_text.strip())}
    if lexer_text.strip():
        lexer_file = _write_lexer_file(run_dir, lexer_name, lexer_text)
        lexer_block["path"] = _relative(lexer_file)
        try:
            lexer_info = read_lexer_token_info(str(lexer_file))
            consistency = validate_tokens(
                spec.tokens,
                lexer_info.produced_token_names,
                spec.ignored,
            )
            lexer_block.update(
                {
                    "tokens": sorted(lexer_info.produced_token_names),
                    "skippedTokens": sorted(lexer_info.skipped_token_names),
                    "warnings": list(lexer_info.warnings) + consistency.warnings,
                    "errors": consistency.errors,
                }
            )
            response["warnings"].extend(lexer_block["warnings"])
            response["errors"].extend(consistency.errors)
            if input_text.strip() and not consistency.errors:
                lexer_script = ensure_lexer_script(str(lexer_file))
                lexer_output = run_lexer(lexer_script, str(input_file), ignored_tokens=spec.ignored)
                lexer_block["generatedScript"] = _relative(Path(lexer_script))
                lexer_block["output"] = {
                    "tokens": [_token_to_dict(token) for token in lexer_output.tokens],
                    "errors": lexer_output.errors,
                }
                response["errors"].extend(lexer_output.errors)
        except RuntimeError as exc:
            lexer_block.setdefault("warnings", [])
            lexer_block["errors"] = [str(exc)]
            response["errors"].append(str(exc))
    elif input_text.strip():
        warning = "Para parsear una entrada se necesita un lexer."
        lexer_block["warnings"] = [warning]
        lexer_block["errors"] = []
        response["warnings"].append(warning)

    response["lexer"] = lexer_block

    try:
        response["analysis"] = _build_analysis(method, spec, lexer_output, verbose, recover)
    except Exception as exc:
        response["ok"] = False
        response["errors"].append(str(exc))
        response["analysis"] = {"error": str(exc)}

    runtime = run_yapar(
        grammar_file=str(grammar_file),
        lexer_file=str(lexer_file) if lexer_file else None,
        input_file=str(input_file) if input_text.strip() else None,
        method=method,
        dot_file=str(dot_file) if method in {"lr0", "slr", "lalr"} else None,
        json_file=str(json_file) if method in {"lr0", "slr", "lalr"} else None,
        verbose=verbose,
        recover=recover,
    )
    response["console"] = runtime.message
    response["ok"] = bool(response["ok"] and not response["errors"] and runtime.ok)
    if not runtime.ok and runtime.message not in response["errors"]:
        response["errors"].append(runtime.message.splitlines()[-1])

    response["artifacts"] = _collect_artifacts(response, dot_file, json_file)
    return response


def _build_analysis(
    method: str,
    spec: Any,
    lexer_output: Any,
    verbose: bool,
    recover: bool,
) -> dict[str, Any]:
    tokens = list(lexer_output.tokens) if lexer_output is not None else None
    if method == "ll1":
        analyzer = LL1Analyzer(spec)
        data = {
            "kind": "ll1",
            "isCompatible": analyzer.is_ll1,
            "first": {nt: sorted(values) for nt, values in analyzer.first.items() if nt in spec.non_terminals},
            "follow": {nt: sorted(values) for nt, values in analyzer.follow.items()},
            "leftRecursion": sorted(analyzer.left_recursive_non_terminals),
            "conflicts": [
                {
                    "nonTerminal": conflict.non_terminal,
                    "terminal": conflict.terminal,
                    "existing": conflict.existing_text(),
                    "new": conflict.new_text(),
                }
                for conflict in analyzer.conflicts
            ],
            "table": [
                {
                    "nonTerminal": nt,
                    "terminal": terminal,
                    "productions": [format_production(nt, production) for production in productions],
                    "conflict": len(productions) > 1,
                }
                for nt, terminal, productions in analyzer.table_entries()
            ],
            "report": analyzer.report_table(),
        }
        if tokens is not None:
            data["parse"] = _parse_result_to_dict(analyzer.parse(tokens, verbose=verbose, recover=recover))
        return data

    if method == "lr0":
        automaton = LR0Automaton.build(spec)
        return {
            "kind": "lr0",
            "automaton": automaton.to_dict(),
            "stateCount": len(automaton.states),
            "transitionCount": len(automaton.transitions),
        }

    if method == "slr":
        parser = SLRParser(spec)
        data = parser.to_dict()
        data.update(
            {
                "kind": "slr",
                "isCompatible": parser.is_slr1,
                "automaton": parser.automaton.to_dict(),
                "follow": {nt: sorted(values) for nt, values in parser.follow.items()},
            }
        )
        if tokens is not None:
            data["parse"] = _parse_result_to_dict(parser.parse(tokens, verbose=verbose, recover=recover))
        return data

    parser = LALRParser(spec)
    data = parser.to_dict()
    data.update({"kind": "lalr", "isCompatible": parser.is_lalr1})
    if tokens is not None:
        data["parse"] = _parse_result_to_dict(parser.parse(tokens, verbose=verbose, recover=recover))
    return data


def _collect_artifacts(response: dict[str, Any], dot_file: Path, json_file: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    if dot_file.exists():
        artifacts["dot"] = {"path": _relative(dot_file), "content": dot_file.read_text(encoding="utf-8")}
    if json_file.exists():
        artifacts["json"] = {
            "path": _relative(json_file),
            "content": json_file.read_text(encoding="utf-8"),
        }
    else:
        payload = {
            "method": response.get("method"),
            "grammar": response.get("grammar"),
            "analysis": response.get("analysis"),
            "lexer": response.get("lexer"),
        }
        artifacts["json"] = {
            "path": None,
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        }
    return artifacts


def _available_examples() -> list[dict[str, Any]]:
    examples = []
    for demo in DEMO_CONFIGS:
        item = dict(demo)
        item["files"] = {
            key: _file_metadata(value)
            for key, value in {
                "grammar": demo.get("grammar"),
                "lexer": demo.get("lexer"),
                "input": demo.get("input"),
            }.items()
            if value
        }
        examples.append(item)
    return examples


def _file_metadata(path_text: str) -> dict[str, Any]:
    path = _safe_project_path(path_text)
    return {
        "path": _relative(path),
        "name": path.name,
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
    }


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    return {
        "tokens": list(spec.tokens),
        "ignored": sorted(spec.ignored),
        "terminals": sorted(spec.terminals),
        "nonTerminals": list(spec.non_terminals),
        "startSymbol": spec.start_symbol,
        "warnings": list(spec.warnings),
        "productions": [
            {
                "index": index,
                "lhs": production.lhs,
                "rhs": list(production.rhs),
                "text": format_production(production.lhs, production.rhs),
            }
            for index, production in enumerate(spec.productions, start=1)
        ],
    }


def _parse_result_to_dict(result: Any) -> dict[str, Any]:
    token = getattr(result, "token", None)
    return {
        "accepted": bool(getattr(result, "accepted", False)),
        "error": getattr(result, "error", None),
        "expected": sorted(getattr(result, "expected", set()) or set()),
        "errors": list(getattr(result, "errors", []) or []),
        "recovered": bool(getattr(result, "recovered", False)),
        "token": _token_to_dict(token) if token is not None else None,
        "steps": [
            {
                "stack": list(getattr(step, "stack", [])),
                "lookahead": getattr(step, "lookahead", ""),
                "action": getattr(step, "action", ""),
            }
            for step in getattr(result, "steps", [])
        ],
    }


def _token_to_dict(token: Any) -> dict[str, Any]:
    return {
        "type": getattr(token, "type", ""),
        "lexeme": getattr(token, "lexeme", ""),
        "line": getattr(token, "line", None),
        "column": getattr(token, "column", getattr(token, "col", None)),
    }


def _write_lexer_file(run_dir: Path, lexer_name: str, lexer_text: str) -> Path:
    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(lexer_name).name or "lexer.yal")
    suffix = Path(clean_name).suffix.lower()
    if suffix not in {".yal", ".yalex", ".py"}:
        clean_name += ".yal"
    path = run_dir / clean_name
    path.write_text(lexer_text, encoding="utf-8", newline="\n")
    return path


def _new_run_dir() -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = ROOT / "generated" / "web_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _safe_project_path(path_text: str) -> Path:
    candidate = (ROOT / path_text).resolve() if not Path(path_text).is_absolute() else Path(path_text).resolve()
    if not _is_inside(candidate, ROOT):
        raise ValueError("La ruta queda fuera del proyecto.")
    return candidate


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _make_server(host: str, port: int) -> ThreadingHTTPServer:
    for candidate in range(port, port + 20):
        try:
            return ThreadingHTTPServer((host, candidate), YaparWebHandler)
        except OSError:
            continue
    raise OSError(f"No se encontro un puerto libre desde {port} hasta {port + 19}.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Frontend web local para YAPar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args(argv)

    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("text/javascript", ".js")

    server = _make_server(args.host, args.port)
    host, port = server.server_address
    print(f"YAPar Web listo en http://{host}:{port}")
    print("Presione Ctrl+C para detenerlo.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
