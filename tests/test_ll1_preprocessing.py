from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
sys.path.insert(0, str(SYNTACTIC_DIR))

from ll1_analyzer import LL1Analyzer
from token_stream import parse_lexer_output, read_lexer_token_info, validate_tokens
from yalp_parser import YalpParseError, parse_yalp


VALID_GRAMMAR = """
%token NUMBER PLUS TIMES LPAREN RPAREN WS
IGNORE WS
%%
expr:
    term exprp
;
exprp:
    PLUS term exprp
  | epsilon
;
term:
    factor termp
;
termp:
    TIMES factor termp
  | epsilon
;
factor:
    NUMBER
  | LPAREN expr RPAREN
;
"""


class LL1PreprocessingTests(unittest.TestCase):
    def test_valid_ll1_grammar_builds_first_follow_and_table(self) -> None:
        spec = parse_yalp(VALID_GRAMMAR)
        analyzer = LL1Analyzer(spec)

        self.assertEqual(spec.start_symbol, "expr")
        self.assertEqual(analyzer.first["expr"], {"NUMBER", "LPAREN"})
        self.assertIn("$", analyzer.follow["expr"])
        self.assertIn("RPAREN", analyzer.follow["expr"])
        self.assertFalse(analyzer.conflicts)
        self.assertEqual(analyzer.table["expr"]["NUMBER"][0], ["term", "exprp"])

    def test_missing_separator_reports_clear_error(self) -> None:
        with self.assertRaisesRegex(YalpParseError, "Falta el separador"):
            parse_yalp("%token A\ns:\n A\n;")

    def test_undeclared_token_reports_clear_error(self) -> None:
        grammar = """
%token A
%%
s:
    A B
;
"""
        with self.assertRaisesRegex(YalpParseError, "Token usado.*B"):
            parse_yalp(grammar)

    def test_undefined_non_terminal_reports_clear_error(self) -> None:
        grammar = """
%token A
%%
s:
    missing
;
"""
        with self.assertRaisesRegex(YalpParseError, "No terminal usado.*missing"):
            parse_yalp(grammar)

    def test_ll1_conflict_is_reported(self) -> None:
        grammar = """
%token A B
%%
s:
    A
  | A B
;
"""
        spec = parse_yalp(grammar)
        analyzer = LL1Analyzer(spec)

        self.assertTrue(analyzer.conflicts)
        conflict = analyzer.conflicts[0]
        self.assertEqual(conflict.non_terminal, "s")
        self.assertEqual(conflict.terminal, "A")
        self.assertEqual(conflict.existing, ["A"])
        self.assertEqual(conflict.new, ["A", "B"])

    def test_missing_semicolon_reports_clear_error(self) -> None:
        grammar = """
%token A
%%
s:
    A
"""
        with self.assertRaisesRegex(YalpParseError, "Falta ';'"):
            parse_yalp(grammar)

    def test_yalex_token_info_matches_declared_yapar_tokens(self) -> None:
        yalex_file = ROOT / "Analizador Lexico" / "examples" / "calculator.yal"
        info = read_lexer_token_info(str(yalex_file))

        self.assertIn("NUMBER", info.token_names)
        self.assertIn("PLUS", info.token_names)
        self.assertEqual(info.eof_token, "EOF")

        declared = {
            "NUMBER",
            "PLUS",
            "MINUS",
            "TIMES",
            "DIV",
            "LPAREN",
            "RPAREN",
            "WS",
        }
        report = validate_tokens(declared, info.produced_token_names, {"WS"})
        self.assertFalse(report.errors)

    def test_lexer_output_accepts_token_names_with_spaces(self) -> None:
        output = parse_lexer_output(
            ['TOKEN MENOR QUE "<" (line 1, col 1)']
        )

        self.assertEqual(len(output.tokens), 1)
        self.assertEqual(output.tokens[0].type, "MENOR QUE")
        self.assertEqual(output.tokens[0].column, 1)


if __name__ == "__main__":
    unittest.main()
