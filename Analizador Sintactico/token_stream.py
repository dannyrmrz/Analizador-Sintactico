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

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Set


@dataclass(frozen=True)
class Token:
    """Representa un token producido por el lexer."""

    type: str
    lexeme: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.lexeme!r}, line={self.line}, col={self.col})"


EOF_TOKEN = Token(type="$", lexeme="<EOF>", line=-1, col=-1)

_TOKEN_RE = re.compile(
    r"^TOKEN\s+"
    r"(?P<type>[A-Za-z_][A-Za-z_0-9]*)\s+"
    r'(?P<lexeme>"(?:[^"\\]|\\.)*")\s+'
    r"\(line\s+(?P<line>\d+),\s*col\s+(?P<col>\d+)\)\s*$"
)

_ERROR_RE = re.compile(
    r"^LEXICAL_ERROR\s+line\s+(?P<line>\d+)\s+col\s+(?P<col>\d+):\s*(?P<byte>.+)$"
)

_SKIP_TYPES = {"SKIP"}


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
            token_type = token_match.group("type")
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
