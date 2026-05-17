"""
lalr_parser.py
==============
Base documentada para LALR(1).

El repo no tenia implementacion LALR previa. Este modulo deja una frontera
limpia para la interfaz/CLI sin afirmar que LALR ya este completo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class LALRStatus:
    implemented: bool
    summary: str
    pending: List[str]


def lalr_status() -> LALRStatus:
    return LALRStatus(
        implemented=False,
        summary="LALR(1) aun no esta implementado en este repositorio.",
        pending=[
            "Construir coleccion canonica LR(1) con lookaheads.",
            "Fusionar estados con el mismo core LR(0).",
            "Combinar lookaheads al fusionar estados.",
            "Construir ACTION/GOTO LALR y detectar conflictos.",
            "Conectar el parser LALR al TokenStream de YALex.",
        ],
    )


def build_lalr_table(*_args: object, **_kwargs: object) -> None:
    status = lalr_status()
    raise NotImplementedError(status.summary)
