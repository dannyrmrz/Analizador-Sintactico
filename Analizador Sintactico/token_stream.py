"""
token_stream.py
===============
Puente entre la salida del lexer generado por YALex y el analizador sintáctico.

El lexer generado imprime líneas con el formato:
    TOKEN <NOMBRE> "<lexema>" (line L, col C)
    LEXICAL_ERROR line L col C: "<byte>"

Este módulo:
  1. Ejecuta el lexer generado sobre un archivo de entrada, O
  2. Lee una lista de líneas ya producidas por el lexer.
  3. Convierte cada línea en un objeto Token que el parser puede consumir.
  4. Ignora tokens marcados como SKIP (espacios en blanco, comentarios).
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Iterator


# ──────────────────────────────────────────────────────────────────────────────
# Estructura básica de token
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Token:
    """Representa un token producido por el lexer."""
    type: str          # Nombre del token (p. ej. 'ID', 'PLUS', 'EOF')
    lexeme: str        # Valor del lexema tal como apareció en el fuente
    line: int          # Línea donde se encontró
    col: int           # Columna donde se encontró

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.lexeme!r}, line={self.line}, col={self.col})"


# Marcador especial de fin de entrada
EOF_TOKEN = Token(type="$", lexeme="<EOF>", line=-1, col=-1)

# ──────────────────────────────────────────────────────────────────────────────
# Parseo de la salida textual del lexer
# ──────────────────────────────────────────────────────────────────────────────

# Patrón para líneas válidas del lexer:
#   TOKEN NOMBRE "lexema" (line L, col C)
_TOKEN_RE = re.compile(
    r'^TOKEN\s+'
    r'(?P<type>[A-Za-z_][A-Za-z_0-9]*)\s+'
    r'(?P<lexeme>"(?:[^"\\]|\\.)*")\s+'
    r'\(line\s+(?P<line>\d+),\s*col\s+(?P<col>\d+)\)\s*$'
)

# Patrón para errores léxicos:
#   LEXICAL_ERROR line L col C: "byte"
_ERROR_RE = re.compile(
    r'^LEXICAL_ERROR\s+line\s+(?P<line>\d+)\s+col\s+(?P<col>\d+):\s*(?P<byte>.+)$'
)

# Tokens que siempre se saltan (generados con 'return lexbuf' o skip=True)
_SKIP_TYPES = {"SKIP"}


@dataclass
class LexerOutput:
    """Resultado del análisis léxico: lista de tokens y lista de errores."""
    tokens: List[Token] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def has_errors(self) -> bool:
        return bool(self.errors)


def parse_lexer_output(
    lines: List[str],
    skip_types: Optional[set] = None,
    ignored_tokens: Optional[set] = None,
) -> LexerOutput:
    """
    Convierte las líneas de texto producidas por el lexer en una LexerOutput.

    Parámetros
    ----------
    lines:
        Líneas tal como las imprime el lexer generado.
    skip_types:
        Nombres de token que se deben ignorar (además de SKIP).
        Por defecto, sólo se ignora 'SKIP'.
    ignored_tokens:
        Conjunto extra de nombres de token a ignorar (viene del IGNORE del .yalp).
    """
    if skip_types is None:
        skip_types = set()
    all_skip = _SKIP_TYPES | skip_types | (ignored_tokens or set())

    result = LexerOutput()
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            continue

        m = _TOKEN_RE.match(line)
        if m:
            tok_type = m.group("type")
            if tok_type in all_skip:
                continue
            # El lexema viene entre comillas dobles; lo decodificamos
            raw_lexeme = m.group("lexeme")        # incluye las comillas
            lexeme = _decode_lexeme(raw_lexeme)
            tok = Token(
                type=tok_type,
                lexeme=lexeme,
                line=int(m.group("line")),
                col=int(m.group("col")),
            )
            result.tokens.append(tok)
            continue

        m = _ERROR_RE.match(line)
        if m:
            msg = (
                f"Error léxico en línea {m.group('line')}, "
                f"columna {m.group('col')}: {m.group('byte')}"
            )
            result.errors.append(msg)
            continue
        # Línea desconocida: ignorar silenciosamente (puede ser debug del lexer)

    return result


def _decode_lexeme(quoted: str) -> str:
    """Elimina las comillas externas y decodifica secuencias de escape simples."""
    inner = quoted[1:-1]  # quita " y "
    return (
        inner
        .replace("\\\\", "\x00BACKSLASH\x00")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\x00BACKSLASH\x00", "\\")
    )


# ──────────────────────────────────────────────────────────────────────────────
# Ejecución del lexer externo
# ──────────────────────────────────────────────────────────────────────────────

def run_lexer(
    lexer_script: str,
    input_file: str,
    python_executable: str = sys.executable,
) -> LexerOutput:
    """
    Ejecuta el lexer generado por YALex sobre *input_file* y retorna
    la lista de tokens.

    Parámetros
    ----------
    lexer_script:
        Ruta al script Python generado por yalexgen (p. ej. 'lexer_generated.py').
    input_file:
        Archivo de texto a analizar léxicamente.
    python_executable:
        Intérprete Python a usar (por defecto el actual).
    """
    try:
        result = subprocess.run(
            [python_executable, lexer_script, input_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"No se pudo ejecutar el lexer '{lexer_script}': {exc}"
        ) from exc

    lines = result.stdout.splitlines()
    return parse_lexer_output(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Stream de tokens (cursor para el parser)
# ──────────────────────────────────────────────────────────────────────────────

class TokenStream:
    """
    Cursor sobre una lista de tokens que el parser puede consumir.

    Siempre termina con EOF_TOKEN para simplificar el manejo del fin de entrada.
    """

    def __init__(self, tokens: List[Token]) -> None:
        self._tokens: List[Token] = list(tokens)
        # Añade centinela al final si el lexer no lo incluyó
        if not self._tokens or self._tokens[-1].type not in ("$", "EOF"):
            self._tokens.append(EOF_TOKEN)
        else:
            # Normaliza EOF del lexer al símbolo $ que usa el parser
            last = self._tokens[-1]
            if last.type == "EOF":
                self._tokens[-1] = Token("$", last.lexeme, last.line, last.col)
        self._pos: int = 0

    # ── Propiedades ─────────────────────────────────────────────────────────

    @property
    def current(self) -> Token:
        """Token en la posición actual (sin consumirlo)."""
        return self._tokens[self._pos]

    @property
    def at_end(self) -> bool:
        """True si el siguiente token es $ (fin de entrada)."""
        return self.current.type == "$"

    # ── Operaciones ─────────────────────────────────────────────────────────

    def peek(self, offset: int = 0) -> Token:
        """
        Devuelve el token en *current_pos + offset* sin avanzar.
        Si se sale del rango, devuelve EOF_TOKEN.
        """
        idx = self._pos + offset
        if idx < len(self._tokens):
            return self._tokens[idx]
        return EOF_TOKEN

    def consume(self) -> Token:
        """Avanza y devuelve el token consumido."""
        tok = self._tokens[self._pos]
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return tok

    def expect(self, token_type: str) -> Token:
        """
        Consume el token actual si su tipo coincide con *token_type*.
        Lanza SyntaxError en caso contrario.
        """
        tok = self.current
        if tok.type != token_type:
            raise SyntaxError(
                f"Se esperaba '{token_type}' pero se encontró '{tok.type}' "
                f"('{tok.lexeme}') en línea {tok.line}, columna {tok.col}"
            )
        return self.consume()

    def __iter__(self) -> Iterator[Token]:
        while not self.at_end:
            yield self.consume()

    def __repr__(self) -> str:
        remaining = self._tokens[self._pos:]
        return f"TokenStream(pos={self._pos}, remaining={remaining[:5]}...)"


# ──────────────────────────────────────────────────────────────────────────────
# Helper: construye un TokenStream desde cualquier fuente
# ──────────────────────────────────────────────────────────────────────────────

def token_stream_from_lexer_output(
    output: LexerOutput,
    raise_on_lex_errors: bool = False,
) -> TokenStream:
    """
    Crea un TokenStream a partir de un LexerOutput.

    Si *raise_on_lex_errors* es True y existen errores léxicos,
    lanza un ValueError con todos los mensajes de error.
    """
    if raise_on_lex_errors and output.has_errors():
        msg = "Errores léxicos encontrados:\n" + "\n".join(output.errors)
        raise ValueError(msg)
    return TokenStream(output.tokens)


def token_stream_from_file(
    lexer_script: str,
    input_file: str,
    ignored_tokens: Optional[set] = None,
    raise_on_lex_errors: bool = False,
) -> TokenStream:
    """
    Atajo: ejecuta el lexer sobre *input_file* y devuelve el TokenStream listo.
    """
    output = run_lexer(lexer_script, input_file)
    # Re-parsear con los tokens ignorados del .yalp
    # (run_lexer ya tiene las líneas; en producción integraríamos el ignored_tokens
    #  directamente en parse_lexer_output)
    filtered = LexerOutput(
        tokens=[t for t in output.tokens if t.type not in (ignored_tokens or set())],
        errors=output.errors,
    )
    return token_stream_from_lexer_output(filtered, raise_on_lex_errors)
