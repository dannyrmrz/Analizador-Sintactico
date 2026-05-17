"""
yalp_parser.py
==============
Parser para archivos .yalp/.yapar (especificacion YAPar/YALP).

El archivo se divide en dos secciones:
  1. Declaracion de tokens con %token e IGNORE.
  2. Producciones despues del separador %%.

Este modulo deja la gramatica en una forma canonica para el
preprocesamiento LL(1): tokens declarados, tokens ignorados, terminales,
no terminales, producciones y simbolo inicial.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

EPSILON = "epsilon"
EPSILON_ALIASES = {"epsilon", "EPSILON", "empty", "EMPTY", "ε"}
END_MARKER = "$"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
_TOKEN_LIKE_RE = re.compile(r"^[A-Z_][A-Z_0-9]*$")


class YalpParseError(Exception):
    """Error durante el parseo o validacion del archivo .yalp/.yapar."""

    def __init__(
        self,
        message: str,
        file: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.file = file
        self.line = line
        self.column = column
        self.suggestion = suggestion

    def __str__(self) -> str:
        location = ""
        if self.file:
            location = self.file
            if self.line is not None:
                location += f":{self.line}"
                if self.column is not None:
                    location += f":{self.column}"
            location += ": "
        elif self.line is not None:
            location = f"Linea {self.line}"
            if self.column is not None:
                location += f", columna {self.column}"
            location += ": "

        text = f"{location}{self.message}"
        if self.suggestion:
            text += f"\nSugerencia: {self.suggestion}"
        return text


@dataclass
class Production:
    """Una produccion canonica A -> alpha."""

    lhs: str
    rhs: List[str]

    def __str__(self) -> str:
        return format_production(self.lhs, self.rhs)


@dataclass
class TokenSection:
    """Resultado reusable del parseo de la seccion de tokens."""

    tokens: List[str] = field(default_factory=list)
    ignored: Set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TokenValidationReport:
    """Resultado de validar tokens declarados, ignorados y usados."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    used_terminals: Set[str] = field(default_factory=set)

    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class YalpSpec:
    """Resultado del parseo de un archivo .yalp/.yapar."""

    tokens: List[str]
    ignored: Set[str]
    grammar: Dict[str, List[List[str]]]
    start_symbol: str
    non_terminals: List[str]
    terminals: Set[str]
    productions: List[Production] = field(default_factory=list)
    used_terminals: Set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)

    def is_terminal(self, sym: str) -> bool:
        return sym in self.terminals or sym == END_MARKER

    def is_non_terminal(self, sym: str) -> bool:
        return sym in self.grammar

    def all_symbols(self) -> Set[str]:
        return set(self.terminals) | set(self.non_terminals) | {EPSILON, END_MARKER}

    def to_dict(self) -> Dict[str, object]:
        """Representacion equivalente a la estructura pedida para el avance."""
        return {
            "tokensDeclarados": set(self.tokens),
            "tokensIgnorados": set(self.ignored),
            "terminales": set(self.terminals),
            "noTerminales": set(self.non_terminals),
            "simboloInicial": self.start_symbol,
            "producciones": [
                {"lhs": prod.lhs, "rhs": list(prod.rhs)} for prod in self.productions
            ],
        }

    def __repr__(self) -> str:
        lines = [
            f"Tokens declarados: {self.tokens}",
            f"Tokens ignorados : {sorted(self.ignored)}",
            f"Simbolo inicial  : {self.start_symbol}",
            f"No terminales   : {self.non_terminals}",
            "Producciones:",
        ]
        for prod in self.productions:
            lines.append(f"  {prod}")
        return "\n".join(lines)


def strip_comments(text: str, filename: Optional[str] = None) -> str:
    """Elimina comentarios /* ... */; pueden ocupar varias lineas."""
    output: List[str] = []
    i = 0
    line = 1
    col = 1

    while i < len(text):
        if text.startswith("/*", i):
            start_line, start_col = line, col
            i += 2
            col += 2
            closed = False
            while i < len(text):
                if text.startswith("*/", i):
                    i += 2
                    col += 2
                    closed = True
                    break
                if text[i] == "\n":
                    output.append("\n")
                    i += 1
                    line += 1
                    col = 1
                else:
                    i += 1
                    col += 1
            if not closed:
                raise YalpParseError(
                    "Comentario sin cerrar.",
                    file=filename,
                    line=start_line,
                    column=start_col,
                    suggestion="Cierre el comentario con */.",
                )
            continue

        output.append(text[i])
        if text[i] == "\n":
            line += 1
            col = 1
        else:
            col += 1
        i += 1

    return "".join(output)


def parse_yalp(source: str, filename: Optional[str] = None) -> YalpSpec:
    """
    Parsea el contenido completo de un .yalp/.yapar.

    Lanza YalpParseError con mensajes claros si falta el separador %%,
    si hay producciones mal formadas o si aparecen simbolos inconsistentes.
    """
    clean = strip_comments(source, filename=filename)

    separator_count = clean.count("%%")
    if separator_count == 0:
        raise YalpParseError(
            "Falta el separador '%%' entre tokens y producciones.",
            file=filename,
            suggestion="Agregue %% despues de la seccion de %token/IGNORE.",
        )
    if separator_count > 1:
        raise YalpParseError(
            "El archivo debe contener un solo separador '%%'.",
            file=filename,
        )

    token_section, production_section = clean.split("%%", 1)

    token_info = parse_token_section(token_section, filename=filename)
    grammar, non_terminals, productions = parse_production_section(
        production_section,
        filename=filename,
        base_line=token_section.count("\n") + 1,
    )
    start_symbol = non_terminals[0]

    validation = validate_declared_tokens(
        declared_tokens=token_info.tokens,
        ignored_tokens=token_info.ignored,
        grammar=grammar,
        non_terminals=non_terminals,
    )
    if validation.has_errors():
        raise YalpParseError(
            _format_validation_errors(validation.errors),
            file=filename,
            suggestion="Revise que los terminales esten declarados con %token y que los no terminales tengan produccion.",
        )

    warnings = token_info.warnings + validation.warnings

    return YalpSpec(
        tokens=token_info.tokens,
        ignored=token_info.ignored,
        grammar=grammar,
        start_symbol=start_symbol,
        non_terminals=non_terminals,
        terminals=set(token_info.tokens),
        productions=productions,
        used_terminals=validation.used_terminals,
        warnings=warnings,
    )


def parse_token_section(
    token_section: str,
    filename: Optional[str] = None,
) -> TokenSection:
    """
    Parsea la seccion previa a %%.

    Soporta:
      %token A
      %token B C D
      IGNORE WS
      IGNORE WS COMMENT
    """
    return _parse_token_section(token_section, filename=filename)


def _parse_token_section(token_section: str, filename: Optional[str] = None) -> TokenSection:
    result = TokenSection()
    seen: Set[str] = set()

    for line_number, raw_line in enumerate(token_section.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        token_match = re.match(r"^%token\s+(.+)$", line)
        if token_match:
            names = token_match.group(1).split()
            if not names:
                raise YalpParseError(
                    "%token no declara tokens.",
                    file=filename,
                    line=line_number,
                    suggestion="Declare al menos un token despues de %token.",
                )
            for name in names:
                _validate_token_name(name, line_number, filename, "token")
                if name in seen:
                    result.warnings.append(f"Token duplicado ignorado: {name}")
                    continue
                result.tokens.append(name)
                seen.add(name)
            continue

        ignore_match = re.match(r"^IGNORE\s+(.+)$", line)
        if ignore_match:
            names = ignore_match.group(1).split()
            if not names:
                raise YalpParseError(
                    "IGNORE no declara tokens.",
                    file=filename,
                    line=line_number,
                    suggestion="Declare al menos un token despues de IGNORE.",
                )
            for name in names:
                _validate_token_name(name, line_number, filename, "token ignorado")
                result.ignored.add(name)
            continue

        raise YalpParseError(
            f"Linea inesperada en seccion de tokens: {line!r}",
            file=filename,
            line=line_number,
            suggestion="Use %token TOKEN_NAME o IGNORE TOKEN_NAME antes de %%.",
        )

    if not result.tokens:
        raise YalpParseError(
            "No se declaro ningun token con %token.",
            file=filename,
            suggestion="La primera seccion debe declarar tokens con %token.",
        )

    return result


def get_ignored_tokens(spec_or_section: object) -> Set[str]:
    """Devuelve los tokens marcados con IGNORE desde YalpSpec o TokenSection."""
    ignored = getattr(spec_or_section, "ignored", None)
    return set(ignored or set())


def parse_production_section(
    production_section: str,
    filename: Optional[str] = None,
    base_line: int = 1,
) -> Tuple[Dict[str, List[List[str]]], List[str], List[Production]]:
    """Parsea la seccion posterior a %% y retorna gramatica canonica."""
    tokens = _tokenize_productions(production_section, filename=filename, base_line=base_line)
    if not tokens:
        raise YalpParseError(
            "La seccion de producciones esta vacia.",
            file=filename,
            line=base_line,
            suggestion="Declare al menos una produccion despues de %%.",
        )

    grammar: Dict[str, List[List[str]]] = {}
    non_terminals: List[str] = []
    productions: List[Production] = []

    i = 0
    while i < len(tokens):
        head = tokens[i]
        if head in {":", "|", ";"}:
            raise YalpParseError(
                f"Se esperaba un nombre de produccion, se encontro {head!r}.",
                file=filename,
                suggestion="Cada produccion debe iniciar con un no terminal.",
            )
        _validate_identifier(head, None, "no terminal", filename=filename)
        i += 1

        if i >= len(tokens) or tokens[i] != ":":
            raise YalpParseError(
                f"Se esperaba ':' despues de la produccion '{head}'.",
                file=filename,
                suggestion=f"Escriba '{head}: ... ;'.",
            )
        i += 1

        if head not in grammar:
            grammar[head] = []
            non_terminals.append(head)

        current_alt: List[str] = []
        closed = False

        while i < len(tokens):
            symbol = tokens[i]
            i += 1

            if symbol == ";":
                _append_production(grammar, productions, head, current_alt)
                closed = True
                break

            if symbol == "|":
                _append_production(grammar, productions, head, current_alt)
                current_alt = []
                continue

            if symbol == ":":
                raise YalpParseError(
                    f"':' inesperado dentro de la produccion '{head}'.",
                    file=filename,
                )

            normalized = normalize_epsilon(symbol)
            if normalized == EPSILON:
                if current_alt:
                    raise YalpParseError(
                        f"epsilon debe aparecer solo en una alternativa: "
                        f"{head} -> {' '.join(current_alt + [symbol])}",
                        file=filename,
                    )
                current_alt = [EPSILON]
                continue

            _validate_identifier(normalized, None, "simbolo de produccion", filename=filename)
            if current_alt == [EPSILON]:
                raise YalpParseError(
                    f"epsilon debe aparecer solo en una alternativa: "
                    f"{head} -> {' '.join(current_alt + [normalized])}",
                    file=filename,
                )
            current_alt.append(normalized)

        if not closed:
            raise YalpParseError(
                f"Falta ';' para cerrar la produccion '{head}'.",
                file=filename,
                suggestion="Termine cada produccion con punto y coma (;).",
            )

    if not grammar:
        raise YalpParseError(
            "La seccion de producciones esta vacia.",
            file=filename,
            line=base_line,
        )

    return grammar, non_terminals, productions


def validate_declared_tokens(
    declared_tokens: Sequence[str],
    ignored_tokens: Iterable[str],
    grammar: Dict[str, List[List[str]]],
    non_terminals: Sequence[str],
) -> TokenValidationReport:
    """
    Valida consistencia basica entre tokens declarados y simbolos RHS.

    - Un simbolo RHS declarado con %token es terminal.
    - Un simbolo RHS definido como LHS es no terminal.
    - Un simbolo desconocido en mayusculas se reporta como token no declarado.
    - Un simbolo desconocido en minusculas/mixto se reporta como no terminal no definido.
    """
    report = TokenValidationReport()
    token_set = set(declared_tokens)
    ignored_set = set(ignored_tokens)
    non_terminal_set = set(non_terminals)

    overlap = token_set & non_terminal_set
    if overlap:
        report.errors.append(
            "Simbolos declarados como token y como no terminal: "
            + ", ".join(sorted(overlap))
        )

    unknown_ignored = ignored_set - token_set
    if unknown_ignored:
        report.errors.append(
            "Tokens en IGNORE no declarados con %token: "
            + ", ".join(sorted(unknown_ignored))
        )

    for head, alternatives in grammar.items():
        for rhs in alternatives:
            if rhs == [EPSILON]:
                continue
            for symbol in rhs:
                if symbol == EPSILON:
                    continue
                production_text = format_production(head, rhs)
                if symbol in token_set:
                    report.used_terminals.add(symbol)
                    if symbol in ignored_set:
                        report.warnings.append(
                            f"Token ignorado usado en producciones: {symbol} "
                            f"en {production_text}"
                        )
                    continue
                if symbol in non_terminal_set:
                    continue
                if _looks_like_token(symbol):
                    report.errors.append(
                        f"Token usado en producciones no declarado con %token: "
                        f"{symbol} en {production_text}"
                    )
                else:
                    report.errors.append(
                        f"No terminal usado pero no definido: "
                        f"{symbol} en {production_text}"
                    )

    unused_tokens = token_set - report.used_terminals - ignored_set
    if unused_tokens:
        report.warnings.append(
            "Tokens declarados no usados en producciones: "
            + ", ".join(sorted(unused_tokens))
        )

    return report


def normalize_epsilon(symbol: str) -> str:
    """Normaliza epsilon, EPSILON, empty y epsilon griego al simbolo interno."""
    return EPSILON if symbol in EPSILON_ALIASES else symbol


def format_production(lhs: str, rhs: Sequence[str]) -> str:
    rhs_text = " ".join(rhs) if rhs else EPSILON
    return f"{lhs} -> {rhs_text}"


def parse_yalp_file(path: str) -> YalpSpec:
    """Lee y parsea un archivo .yalp/.yapar desde disco."""
    try:
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
    except OSError as exc:
        raise YalpParseError(
            f"No se pudo leer el archivo: {exc}",
            file=path,
            suggestion="Verifique que la ruta exista y tenga permisos de lectura.",
        ) from exc
    return parse_yalp(content, filename=path)


def _append_production(
    grammar: Dict[str, List[List[str]]],
    productions: List[Production],
    head: str,
    rhs: List[str],
) -> None:
    normalized_rhs = rhs if rhs else [EPSILON]
    grammar[head].append(list(normalized_rhs))
    productions.append(Production(head, list(normalized_rhs)))


def _tokenize_productions(
    text: str,
    filename: Optional[str] = None,
    base_line: int = 1,
) -> List[str]:
    """Tokeniza nombres y separadores ':', '|' y ';'."""
    text = strip_comments(text, filename=filename)
    token_re = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|[:|;]|\S")
    result: List[str] = []

    for match in token_re.finditer(text):
        value = match.group(0)
        if _IDENTIFIER_RE.match(value) or value in {":", "|", ";"}:
            result.append(value)
            continue

        line, col = _line_col(text, match.start())
        raise YalpParseError(
            f"Simbolo invalido en producciones en linea {line}, columna {col}: "
            f"{value!r}",
            file=filename,
            line=base_line + line - 1,
            column=col,
            suggestion="Use identificadores, ':', '|', ';' o epsilon.",
        )

    return result


def _validate_identifier(
    name: str,
    line_number: Optional[int],
    context: str,
    filename: Optional[str] = None,
) -> None:
    if _IDENTIFIER_RE.match(name):
        return
    raise YalpParseError(
        f"Nombre invalido para {context}: {name!r}",
        file=filename,
        line=line_number,
        suggestion="Use letras, digitos y guion bajo; no inicie con digito.",
    )


def _validate_token_name(
    name: str,
    line_number: Optional[int],
    filename: Optional[str],
    context: str,
) -> None:
    _validate_identifier(name, line_number, context, filename=filename)
    if _TOKEN_LIKE_RE.match(name):
        return
    raise YalpParseError(
        f"Nombre invalido para {context}: {name!r}. Los tokens deben ir en mayusculas.",
        file=filename,
        line=line_number,
        suggestion="Use nombres como ID, NUMBER, PLUS o TOKEN_NAME.",
    )


def _looks_like_token(symbol: str) -> bool:
    return bool(_TOKEN_LIKE_RE.match(symbol))


def _line_col(text: str, index: int) -> Tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    last_newline = text.rfind("\n", 0, index)
    col = index + 1 if last_newline == -1 else index - last_newline
    return line, col


def _format_validation_errors(errors: Sequence[str]) -> str:
    lines = ["Errores de validacion de la gramatica:"]
    lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)
