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


def strip_comments(text: str) -> str:
    """Elimina comentarios /* ... */; pueden ocupar varias lineas."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def parse_yalp(source: str) -> YalpSpec:
    """
    Parsea el contenido completo de un .yalp/.yapar.

    Lanza YalpParseError con mensajes claros si falta el separador %%,
    si hay producciones mal formadas o si aparecen simbolos inconsistentes.
    """
    clean = strip_comments(source)

    separator_count = clean.count("%%")
    if separator_count == 0:
        raise YalpParseError("Falta el separador '%%' entre tokens y producciones.")
    if separator_count > 1:
        raise YalpParseError("El archivo debe contener un solo separador '%%'.")

    token_section, production_section = clean.split("%%", 1)

    token_info = parse_token_section(token_section)
    grammar, non_terminals, productions = parse_production_section(production_section)
    start_symbol = non_terminals[0]

    validation = validate_declared_tokens(
        declared_tokens=token_info.tokens,
        ignored_tokens=token_info.ignored,
        grammar=grammar,
        non_terminals=non_terminals,
    )
    if validation.has_errors():
        raise YalpParseError(_format_validation_errors(validation.errors))

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


def parse_token_section(token_section: str) -> TokenSection:
    """
    Parsea la seccion previa a %%.

    Soporta:
      %token A
      %token B C D
      IGNORE WS
      IGNORE WS COMMENT
    """
    result = TokenSection()
    seen: Set[str] = set()

    for line_number, raw_line in enumerate(token_section.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        token_match = re.match(r"^%token\s+(.+)$", line, re.IGNORECASE)
        if token_match:
            names = token_match.group(1).split()
            if not names:
                raise YalpParseError(f"Linea {line_number}: %token no declara tokens.")
            for name in names:
                _validate_identifier(name, line_number, "token")
                if name in seen:
                    result.warnings.append(f"Token duplicado ignorado: {name}")
                    continue
                result.tokens.append(name)
                seen.add(name)
            continue

        ignore_match = re.match(r"^IGNORE\s+(.+)$", line, re.IGNORECASE)
        if ignore_match:
            names = ignore_match.group(1).split()
            if not names:
                raise YalpParseError(f"Linea {line_number}: IGNORE no declara tokens.")
            for name in names:
                _validate_identifier(name, line_number, "token ignorado")
                result.ignored.add(name)
            continue

        raise YalpParseError(
            f"Linea {line_number}: linea inesperada en seccion de tokens: {line!r}"
        )

    if not result.tokens:
        raise YalpParseError("No se declaro ningun token con %token.")

    return result


def get_ignored_tokens(spec_or_section: object) -> Set[str]:
    """Devuelve los tokens marcados con IGNORE desde YalpSpec o TokenSection."""
    ignored = getattr(spec_or_section, "ignored", None)
    return set(ignored or set())


def parse_production_section(
    production_section: str,
) -> Tuple[Dict[str, List[List[str]]], List[str], List[Production]]:
    """Parsea la seccion posterior a %% y retorna gramatica canonica."""
    tokens = _tokenize_productions(production_section)
    if not tokens:
        raise YalpParseError("La seccion de producciones esta vacia.")

    grammar: Dict[str, List[List[str]]] = {}
    non_terminals: List[str] = []
    productions: List[Production] = []

    i = 0
    while i < len(tokens):
        head = tokens[i]
        if head in {":", "|", ";"}:
            raise YalpParseError(
                f"Se esperaba un nombre de produccion, se encontro {head!r}."
            )
        _validate_identifier(head, None, "no terminal")
        i += 1

        if i >= len(tokens) or tokens[i] != ":":
            raise YalpParseError(f"Se esperaba ':' despues de la produccion '{head}'.")
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
                    f"':' inesperado dentro de la produccion '{head}'."
                )

            normalized = normalize_epsilon(symbol)
            if normalized == EPSILON:
                if current_alt:
                    raise YalpParseError(
                        f"epsilon debe aparecer solo en una alternativa: "
                        f"{head} -> {' '.join(current_alt + [symbol])}"
                    )
                current_alt = [EPSILON]
                continue

            _validate_identifier(normalized, None, "simbolo de produccion")
            if current_alt == [EPSILON]:
                raise YalpParseError(
                    f"epsilon debe aparecer solo en una alternativa: "
                    f"{head} -> {' '.join(current_alt + [normalized])}"
                )
            current_alt.append(normalized)

        if not closed:
            raise YalpParseError(
                f"Falta ';' para cerrar la produccion '{head}'."
            )

    if not grammar:
        raise YalpParseError("La seccion de producciones esta vacia.")

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
        raise YalpParseError(f"No se pudo leer el archivo: {exc}") from exc
    return parse_yalp(content)


def _append_production(
    grammar: Dict[str, List[List[str]]],
    productions: List[Production],
    head: str,
    rhs: List[str],
) -> None:
    normalized_rhs = rhs if rhs else [EPSILON]
    grammar[head].append(list(normalized_rhs))
    productions.append(Production(head, list(normalized_rhs)))


def _tokenize_productions(text: str) -> List[str]:
    """Tokeniza nombres y separadores ':', '|' y ';'."""
    text = strip_comments(text)
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
            f"{value!r}"
        )

    return result


def _validate_identifier(name: str, line_number: Optional[int], context: str) -> None:
    if _IDENTIFIER_RE.match(name):
        return
    prefix = f"Linea {line_number}: " if line_number is not None else ""
    raise YalpParseError(f"{prefix}Nombre invalido para {context}: {name!r}")


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
