"""
token_stream.py
===============
Puente entre la salida del lexer generado por YALex y el parser.

El lexer generado imprime lineas como:
    TOKEN NAME "lexeme" (line L, col C)
    LEXICAL_ERROR line L col C: "byte"

Este modulo convierte esa salida en objetos Token, filtra tokens ignorados
por YAPar y deja una funcion de validacion para comparar tokens YAPar/YALex.
"""
from __future__ import annotations

import ast as py_ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set


@dataclass(frozen=True)
class Token:
    """Representa un token producido por el lexer."""

    type: str
    lexeme: str
    line: int
    col: int

    @property
    def column(self) -> int:
        """Alias compatible con la nomenclatura line/column."""
        return self.col

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.lexeme!r}, line={self.line}, col={self.col})"


EOF_TOKEN = Token(type="$", lexeme="<EOF>", line=-1, col=-1)

_TOKEN_RE = re.compile(
    r"^TOKEN\s+"
    r"(?P<type>.+?)\s+"
    r'(?P<lexeme>"(?:[^"\\]|\\.)*")\s+'
    r"\(line\s+(?P<line>\d+),\s*col\s+(?P<col>\d+)\)\s*$"
)

_ERROR_RE = re.compile(
    r"^LEXICAL_ERROR\s+line\s+(?P<line>\d+)\s+col\s+(?P<col>\d+):\s*(?P<byte>.+)$"
)

_SKIP_TYPES = {"SKIP"}
_YAPAR_TOKEN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


@dataclass
class LexerTokenInfo:
    """Tokens declarados/producidos por una especificacion o lexer YALex."""

    token_names: List[str] = field(default_factory=list)
    skipped_token_names: Set[str] = field(default_factory=set)
    eof_token: Optional[str] = None
    source: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def produced_token_names(self) -> Set[str]:
        names = set(self.token_names)
        if self.eof_token:
            names.add(self.eof_token)
        return names


@dataclass
class LexerOutput:
    """Resultado del analisis lexico."""

    tokens: List[Token] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class TokenConsistencyReport:
    """Resultado de comparar tokens declarados en YAPar contra tokens de YALex."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    declared_tokens: Set[str] = field(default_factory=set)
    ignored_tokens: Set[str] = field(default_factory=set)
    produced_token_names: Set[str] = field(default_factory=set)

    def has_errors(self) -> bool:
        return bool(self.errors)


def parse_lexer_output(
    lines: List[str],
    skip_types: Optional[Set[str]] = None,
    ignored_tokens: Optional[Set[str]] = None,
) -> LexerOutput:
    """Convierte lineas impresas por el lexer en LexerOutput."""
    all_skip = _SKIP_TYPES | set(skip_types or set()) | set(ignored_tokens or set())

    result = LexerOutput()
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            continue

        token_match = _TOKEN_RE.match(line)
        if token_match:
            token_type = token_match.group("type").strip()
            if token_type in all_skip:
                continue
            result.tokens.append(
                Token(
                    type=token_type,
                    lexeme=_decode_lexeme(token_match.group("lexeme")),
                    line=int(token_match.group("line")),
                    col=int(token_match.group("col")),
                )
            )
            continue

        error_match = _ERROR_RE.match(line)
        if error_match:
            result.errors.append(
                "Error lexico en linea "
                f"{error_match.group('line')}, columna {error_match.group('col')}: "
                f"{error_match.group('byte')}"
            )

    return result


def validate_tokens(
    declared_tokens: Iterable[str],
    produced_token_names: Optional[Iterable[object]] = None,
    ignored_tokens: Optional[Iterable[str]] = None,
) -> TokenConsistencyReport:
    """
    Valida consistencia basica entre YAPar y YALex.

    - declared_tokens viene de %token.
    - ignored_tokens viene de IGNORE.
    - produced_token_names puede contener strings o instancias Token.
    """
    declared = set(declared_tokens)
    ignored = set(ignored_tokens or set())
    produced = _normalize_token_names(produced_token_names or [])

    report = TokenConsistencyReport(
        declared_tokens=declared,
        ignored_tokens=ignored,
        produced_token_names=produced,
    )

    unknown_ignored = ignored - declared
    if unknown_ignored:
        report.errors.append(
            "Tokens en IGNORE no declarados con %token: "
            + ", ".join(sorted(unknown_ignored))
        )

    if produced:
        special = {"$", "EOF", "SKIP"}
        invalid_names = {
            name
            for name in produced
            if name not in special and not _YAPAR_TOKEN_NAME_RE.match(name)
        }
        if invalid_names:
            report.errors.append(
                "Tokens producidos por YALex no son identificadores validos para YAPar: "
                + ", ".join(sorted(invalid_names))
            )

        undeclared = produced - declared - ignored - special
        if undeclared:
            report.errors.append(
                "Tokens producidos por YALex no declarados en YAPar: "
                + ", ".join(sorted(undeclared))
            )

        missing_in_lexer = declared - produced - ignored
        if missing_in_lexer:
            report.warnings.append(
                "Tokens declarados en YAPar no observados/producidos por YALex: "
                + ", ".join(sorted(missing_in_lexer))
            )

    return report


def read_lexer_token_info(lexer_path: str) -> LexerTokenInfo:
    """
    Lee tokens desde una especificacion `.yal/.yalex` o un lexer Python generado.

    Si la ruta termina en `.yal` o `.yalex`, se reutiliza el parser de YALex.
    En cualquier otro caso se interpreta como lexer generado y se leen las
    asignaciones `TOKEN_NAMES`, `TOKEN_SKIP`, `EOF_TOKEN` y `EOF_SKIP`.
    """
    path = Path(lexer_path)
    if path.suffix.lower() in {".yal", ".yalex"}:
        return read_yalex_spec_token_info(str(path))
    return read_generated_lexer_token_info(str(path))


def read_yalex_spec_token_info(yalex_path: str) -> LexerTokenInfo:
    """Extrae nombres de tokens directamente desde un archivo YALex."""
    _ensure_yalex_on_path()

    try:
        from src_py.emit import infer_token_name, is_eof_regex
        from src_py.util import read_file
        from src_py.yal_spec import parse_spec, yal_strip_comments
    except Exception as exc:  # pragma: no cover - depende del layout del repo.
        raise RuntimeError(f"No se pudo cargar el generador YALex: {exc}") from exc

    try:
        spec = parse_spec(yal_strip_comments(read_file(yalex_path)))
    except Exception as exc:
        raise RuntimeError(f"No se pudieron leer tokens desde YALex '{yalex_path}': {exc}") from exc

    info = LexerTokenInfo(source=yalex_path)
    for index, rule in enumerate(spec.rules):
        name, skip = infer_token_name(rule.action, index)
        if is_eof_regex(rule.regex):
            if skip:
                info.skipped_token_names.add(name)
            else:
                info.eof_token = name
            continue
        if skip:
            info.skipped_token_names.add(name)
            continue
        _append_unique(info.token_names, name)

    info.warnings.extend(_invalid_token_name_warnings(info.produced_token_names))
    return info


def read_generated_lexer_token_info(lexer_path: str) -> LexerTokenInfo:
    """Extrae nombres de tokens desde el lexer Python emitido por YALex."""
    try:
        source = Path(lexer_path).read_text(encoding="utf-8")
        tree = py_ast.parse(source, filename=lexer_path)
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer el lexer generado '{lexer_path}': {exc}") from exc
    except UnicodeError as exc:
        raise RuntimeError(
            f"El lexer generado '{lexer_path}' no se pudo leer como texto UTF-8: {exc}"
        ) from exc
    except SyntaxError as exc:
        raise RuntimeError(f"El lexer generado no es Python valido '{lexer_path}': {exc}") from exc

    assignments = _literal_assignments(tree, {"TOKEN_NAMES", "TOKEN_SKIP", "EOF_TOKEN", "EOF_SKIP"})
    if "TOKEN_NAMES" not in assignments:
        raise RuntimeError(
            f"El archivo '{lexer_path}' no parece ser un lexer generado por YALex "
            "(falta TOKEN_NAMES)."
        )

    token_names = list(assignments.get("TOKEN_NAMES") or [])
    token_skip = list(assignments.get("TOKEN_SKIP") or [0] * len(token_names))
    eof_token = assignments.get("EOF_TOKEN")
    eof_skip = bool(assignments.get("EOF_SKIP", False))

    info = LexerTokenInfo(source=lexer_path)
    for index, name in enumerate(token_names):
        skip = bool(token_skip[index]) if index < len(token_skip) else False
        if skip:
            info.skipped_token_names.add(str(name))
        else:
            _append_unique(info.token_names, str(name))

    if eof_token is not None:
        if eof_skip:
            info.skipped_token_names.add(str(eof_token))
        else:
            info.eof_token = str(eof_token)

    info.warnings.extend(_invalid_token_name_warnings(info.produced_token_names))
    return info


def run_lexer(
    lexer_script: str,
    input_file: str,
    python_executable: str = sys.executable,
    ignored_tokens: Optional[Set[str]] = None,
) -> LexerOutput:
    """Ejecuta el lexer generado por YALex sobre input_file."""
    try:
        result = subprocess.run(
            [python_executable, lexer_script, input_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"No se pudo ejecutar el lexer '{lexer_script}': {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"El lexer '{lexer_script}' termino con codigo {result.returncode}."
            + (f" Detalle: {detail}" if detail else "")
        )

    return parse_lexer_output(result.stdout.splitlines(), ignored_tokens=ignored_tokens)


class TokenStream:
    """Cursor sobre tokens para el parser predictivo futuro."""

    def __init__(self, tokens: List[Token]) -> None:
        self._tokens: List[Token] = list(tokens)
        if not self._tokens or self._tokens[-1].type not in ("$", "EOF"):
            self._tokens.append(EOF_TOKEN)
        elif self._tokens[-1].type == "EOF":
            last = self._tokens[-1]
            self._tokens[-1] = Token("$", last.lexeme, last.line, last.col)
        self._pos = 0

    @property
    def current(self) -> Token:
        return self._tokens[self._pos]

    @property
    def at_end(self) -> bool:
        return self.current.type == "$"

    def peek(self, offset: int = 0) -> Token:
        index = self._pos + offset
        if index < len(self._tokens):
            return self._tokens[index]
        return EOF_TOKEN

    def consume(self) -> Token:
        token = self._tokens[self._pos]
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return token

    def expect(self, token_type: str) -> Token:
        token = self.current
        if token.type != token_type:
            raise SyntaxError(
                f"Se esperaba '{token_type}' pero se encontro '{token.type}' "
                f"('{token.lexeme}') en linea {token.line}, columna {token.col}"
            )
        return self.consume()

    def __iter__(self) -> Iterator[Token]:
        while not self.at_end:
            yield self.consume()

    def __repr__(self) -> str:
        remaining = self._tokens[self._pos :]
        return f"TokenStream(pos={self._pos}, remaining={remaining[:5]}...)"


def token_stream_from_lexer_output(
    output: LexerOutput,
    raise_on_lex_errors: bool = False,
) -> TokenStream:
    """Crea un TokenStream desde LexerOutput."""
    if raise_on_lex_errors and output.has_errors():
        message = "Errores lexicos encontrados:\n" + "\n".join(output.errors)
        raise ValueError(message)
    return TokenStream(output.tokens)


def token_stream_from_file(
    lexer_script: str,
    input_file: str,
    ignored_tokens: Optional[Set[str]] = None,
    raise_on_lex_errors: bool = False,
) -> TokenStream:
    """Ejecuta el lexer y devuelve un TokenStream listo."""
    output = run_lexer(lexer_script, input_file, ignored_tokens=ignored_tokens)
    return token_stream_from_lexer_output(output, raise_on_lex_errors)


def _decode_lexeme(quoted: str) -> str:
    inner = quoted[1:-1]
    return (
        inner.replace("\\\\", "\x00BACKSLASH\x00")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\x00BACKSLASH\x00", "\\")
    )


def _normalize_token_names(items: Iterable[object]) -> Set[str]:
    names: Set[str] = set()
    for item in items:
        token_type = getattr(item, "type", None)
        names.add(str(token_type if token_type is not None else item))
    return names


def _ensure_yalex_on_path() -> None:
    lex_dir = Path(__file__).resolve().parents[1] / "Analizador Lexico"
    if str(lex_dir) not in sys.path:
        sys.path.insert(0, str(lex_dir))


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _literal_assignments(tree: py_ast.AST, names: Set[str]) -> dict[str, object]:
    found: dict[str, object] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, py_ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, py_ast.Name) and target.id in names:
                try:
                    found[target.id] = py_ast.literal_eval(node.value)
                except Exception:
                    pass
    return found


def _invalid_token_name_warnings(names: Iterable[str]) -> List[str]:
    special = {"$", "EOF", "SKIP"}
    invalid = sorted(
        name for name in names if name not in special and not _YAPAR_TOKEN_NAME_RE.match(name)
    )
    if not invalid:
        return []
    return [
        "Tokens de YALex no compatibles con nombres YAPar: " + ", ".join(invalid)
    ]
