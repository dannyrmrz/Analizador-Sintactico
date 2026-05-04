"""
yalp_parser.py
==============
Parser para archivos .yalp (especificación YAPar).

Formato esperado:
    /* comentarios */

    %token TOKEN_A
    %token TOKEN_B TOKEN_C
    IGNORE TOKEN_B

    %%

    produccion1:
        produccion1 TOKEN_A produccion2
      | produccion2
      ;

    produccion2:
        TOKEN_C produccion1 TOKEN_A
      | TOKEN_A
      ;

Salida: un objeto YalpSpec con la gramática en forma canónica.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────────────────────────────────────

EPSILON = "ε"      # Símbolo épsilon utilizado en producciones vacías
END_MARKER = "$"   # Marcador de fin de entrada


@dataclass
class YalpSpec:
    """Resultado del parseo de un archivo .yalp."""
    tokens: List[str]                   # Tokens declarados con %token (en orden)
    ignored: Set[str]                   # Tokens marcados con IGNORE
    grammar: Dict[str, List[List[str]]] # No-terminal → lista de alternativas
    start_symbol: str                   # Primera producción = símbolo inicial
    non_terminals: List[str]            # No-terminales en orden de aparición
    terminals: Set[str]                 # Terminales (tokens no ignorados)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def is_terminal(self, sym: str) -> bool:
        return sym in self.terminals or sym == END_MARKER

    def is_non_terminal(self, sym: str) -> bool:
        return sym in self.grammar

    def all_symbols(self) -> Set[str]:
        return set(self.terminals) | set(self.non_terminals) | {EPSILON, END_MARKER}

    def __repr__(self) -> str:
        lines = [
            f"Tokens    : {self.tokens}",
            f"Ignored   : {self.ignored}",
            f"Start     : {self.start_symbol}",
            f"Non-terms : {self.non_terminals}",
            "Grammar:",
        ]
        for nt, prods in self.grammar.items():
            for p in prods:
                lines.append(f"  {nt} -> {' '.join(p)}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Eliminación de comentarios
# ──────────────────────────────────────────────────────────────────────────────

def _strip_comments(text: str) -> str:
    """Elimina comentarios /* ... */ (posiblemente multi-línea)."""
    return re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)


# ──────────────────────────────────────────────────────────────────────────────
# Parser principal
# ──────────────────────────────────────────────────────────────────────────────

class YalpParseError(Exception):
    """Error durante el parseo del archivo .yalp."""


def parse_yalp(source: str) -> YalpSpec:
    """
    Parsea el contenido de un archivo .yalp y retorna un YalpSpec.

    Parámetros
    ----------
    source:
        Contenido completo del archivo .yalp como string.

    Retorna
    -------
    YalpSpec con la gramática lista para ser procesada por el analizador LL(1).
    """
    clean = _strip_comments(source)

    # Dividir en sección de tokens y sección de producciones
    parts = re.split(r'%%', clean, maxsplit=1)
    if len(parts) != 2:
        raise YalpParseError(
            "El archivo .yalp debe contener exactamente un separador '%%'"
        )
    token_section, production_section = parts

    # ── Sección de tokens ────────────────────────────────────────────────────
    tokens: List[str] = []
    ignored: Set[str] = set()

    for line in token_section.splitlines():
        line = line.strip()
        if not line:
            continue

        # %token TOKEN_A TOKEN_B ...
        m = re.match(r'^%token\s+(.+)$', line, re.IGNORECASE)
        if m:
            names = m.group(1).split()
            for name in names:
                name = name.strip()
                if name:
                    tokens.append(name)
            continue

        # IGNORE TOKEN_X
        m = re.match(r'^IGNORE\s+(\S+)\s*$', line, re.IGNORECASE)
        if m:
            ignored.add(m.group(1).strip())
            continue

        # Cualquier otra línea no vacía en la sección de tokens → error
        if line:
            raise YalpParseError(
                f"Línea inesperada en sección de tokens: {line!r}"
            )

    if not tokens:
        raise YalpParseError("No se declaró ningún token con %token")

    # ── Sección de producciones ───────────────────────────────────────────────
    grammar: Dict[str, List[List[str]]] = {}
    non_terminals_order: List[str] = []

    # Tokenizar la sección de producciones
    # Gramática de la sección:
    #   nombre ':' alternativas ';'
    #   alternativas ::= alternativa ('|' alternativa)*
    #   alternativa  ::= símbolo*    (vacía = epsilon)

    # Extraer bloques: <nombre> ':' ... ';'
    prod_text = production_section.strip()

    # Reemplazar saltos de línea por espacios para tokenizar más fácil
    # pero conservamos ';' y '|' y ':'
    tokens_prod = _tokenize_productions(prod_text)

    i = 0
    n = len(tokens_prod)
    while i < n:
        # Nombre del no-terminal
        if tokens_prod[i] == ";":
            i += 1
            continue
        head = tokens_prod[i]
        if not re.match(r'^[A-Za-z_][A-Za-z_0-9]*$', head):
            raise YalpParseError(
                f"Se esperaba un nombre de producción, se encontró: {head!r}"
            )
        i += 1

        # ':'
        if i >= n or tokens_prod[i] != ':':
            raise YalpParseError(
                f"Se esperaba ':' después de '{head}'"
            )
        i += 1

        if head not in grammar:
            grammar[head] = []
            non_terminals_order.append(head)

        # Alternativas hasta ';'
        current_alt: List[str] = []
        while i < n and tokens_prod[i] != ';':
            sym = tokens_prod[i]
            if sym == '|':
                # Guardar alternativa actual
                grammar[head].append(current_alt if current_alt else [EPSILON])
                current_alt = []
            else:
                current_alt.append(sym)
            i += 1

        # Guardar última alternativa
        grammar[head].append(current_alt if current_alt else [EPSILON])

        # Consumir ';'
        if i < n and tokens_prod[i] == ';':
            i += 1

    if not grammar:
        raise YalpParseError("La sección de producciones está vacía")

    start_symbol = non_terminals_order[0]

    # ── Calcular terminales ──────────────────────────────────────────────────
    # Terminales = tokens declarados que no son ignorados Y que aparecen en
    # alguna producción, MÁS cualquier símbolo en las producciones que sea
    # mayúscula (convención YAPar: mayúsculas = terminales).
    non_term_set = set(non_terminals_order)
    terminals: Set[str] = set()
    for prods in grammar.values():
        for prod in prods:
            for sym in prod:
                if sym == EPSILON:
                    continue
                if sym not in non_term_set:
                    terminals.add(sym)

    # Validación suave: verificar que los terminales usados estén declarados
    declared = set(tokens)
    undeclared = terminals - declared
    if undeclared:
        # No es fatal, pero avisamos (pueden ser literales como '+', '-')
        pass  # En YAPar real sería un warning

    return YalpSpec(
        tokens=tokens,
        ignored=ignored,
        grammar=grammar,
        start_symbol=start_symbol,
        non_terminals=non_terminals_order,
        terminals=terminals,
    )


def _tokenize_productions(text: str) -> List[str]:
    """
    Tokeniza el texto de la sección de producciones en una lista de tokens
    (nombres, ':', '|', ';').
    """
    # Eliminar comentarios residuales (por si acaso)
    text = _strip_comments(text)

    # Separar por espacios/newlines, conservando :  |  ;
    # Insertamos espacios alrededor de los operadores especiales
    text = re.sub(r'([:|;])', r' \1 ', text)
    parts = text.split()
    return [p for p in parts if p]


# ──────────────────────────────────────────────────────────────────────────────
# Utilidad: leer desde archivo
# ──────────────────────────────────────────────────────────────────────────────

def parse_yalp_file(path: str) -> YalpSpec:
    """Lee y parsea un archivo .yalp desde disco."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        raise YalpParseError(f"No se pudo leer el archivo: {exc}") from exc
    return parse_yalp(content)
