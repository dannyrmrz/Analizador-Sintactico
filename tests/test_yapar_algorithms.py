from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
sys.path.insert(0, str(SYNTACTIC_DIR))

from ll1_analyzer import LL1Analyzer
from lr0_automaton import LR0Automaton
from slr_parser import SLRParser
from token_stream import Token
from yalp_parser import parse_yalp


LL1_GRAMMAR = """
%token NUMBER PLUS WS
IGNORE WS
%%
expr:
    NUMBER exprp
;
exprp:
    PLUS NUMBER exprp
  | epsilon
;
"""


SLR_LEFT_RECURSIVE = """
%token NUMBER PLUS WS
IGNORE WS
%%
expr:
    expr PLUS NUMBER
  | NUMBER
;
"""


SLR_CONFLICT = """
%token A
%%
s:
    s s
  | A
;
"""


class YaparAlgorithmTests(unittest.TestCase):
    def test_ll1_parser_accepts_token_stream(self) -> None:
        spec = parse_yalp(LL1_GRAMMAR)
        analyzer = LL1Analyzer(spec)
        tokens = [
            Token("NUMBER", "1", 1, 1),
            Token("PLUS", "+", 1, 3),
            Token("NUMBER", "2", 1, 5),
        ]

        result = analyzer.parse(tokens)

        self.assertTrue(result.accepted, result.error)

    def test_ll1_parser_reports_syntax_error(self) -> None:
        spec = parse_yalp(LL1_GRAMMAR)
        analyzer = LL1Analyzer(spec)
        tokens = [
            Token("NUMBER", "1", 1, 1),
            Token("PLUS", "+", 1, 3),
            Token("PLUS", "+", 1, 5),
        ]

        result = analyzer.parse(tokens)

        self.assertFalse(result.accepted)
        self.assertIn("Se encontro PLUS", result.error or "")
        self.assertIn("NUMBER", result.error or "")

    def test_lr0_automaton_builds_augmented_start_and_dot(self) -> None:
        spec = parse_yalp(LL1_GRAMMAR)
        automaton = LR0Automaton.build(spec)
        dot = automaton.to_dot()

        self.assertEqual(automaton.productions[0].lhs, "expr'")
        self.assertGreaterEqual(len(automaton.states), 2)
        self.assertIn("digraph LR0", dot)
        self.assertIn("expr' -> . expr", dot)

    def test_slr_accepts_left_recursive_expression_grammar(self) -> None:
        spec = parse_yalp(SLR_LEFT_RECURSIVE)
        ll1 = LL1Analyzer(spec)
        parser = SLRParser(spec)
        tokens = [
            Token("NUMBER", "1", 1, 1),
            Token("PLUS", "+", 1, 3),
            Token("NUMBER", "2", 1, 5),
        ]

        self.assertFalse(ll1.is_ll1)
        self.assertTrue(parser.is_slr1)
        self.assertTrue(parser.parse(tokens).accepted)

    def test_slr_conflict_is_reported(self) -> None:
        spec = parse_yalp(SLR_CONFLICT)
        parser = SLRParser(spec)

        self.assertFalse(parser.is_slr1)
        self.assertTrue(parser.conflicts)
        self.assertIn("conflict", parser.conflicts[0].conflict_type)


if __name__ == "__main__":
    unittest.main()
