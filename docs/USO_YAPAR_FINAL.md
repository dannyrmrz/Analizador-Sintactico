# Uso de YALex + YAPar

## Como compilar

El proyecto esta escrito en Python. No requiere compilacion.

En esta maquina se uso:

```bash
python --version
```

## Ejecutar YALex

Desde `Analizador Lexico/`:

```bash
python yalexgen examples/calculator.yal -o examples/lexer_generated.py --dot examples/regex_tree.dot --no-png
python examples/lexer_generated.py examples/input_ok.txt
```

## Ejecutar YAPar

Desde la raiz del repo:

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_ok.txt --method slr --dot generated/lr0_automaton.dot
```

El CLI acepta:

- `--method ll1`: tabla y parser LL(1).
- `--method lr0`: construye y exporta automata LR(0).
- `--method slr`: tabla y parser SLR(1).
- `--method lalr`: tabla y parser LALR(1).
- `--dot ruta.dot`: exporta automata LR(0).
- `--json ruta.json`: exporta estructuras para una interfaz.
- `--tree`: muestra el arbol semantico cuando la entrada es aceptada.
- `--tree-json archivo.json`: exporta el arbol semantico en JSON.
- `--tree-dot archivo.dot`: exporta el arbol semantico en DOT.
- `--verbose`: muestra pasos del parser cuando se analiza una entrada.
- `--recover`: activa recuperacion panic-mode para reportar errores sintacticos adicionales.

## Generar runner de parser

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" -o generated/theparser.py --method slr
python generated/theparser.py examples/calculator_input_ok.txt
```

## Probar LL(1)

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_ok.txt --method ll1
```

## Probar LR(0)

```bash
python yapar.py examples/calculator_parser.yalp --method lr0 --dot generated/lr0_automaton.dot --json generated/lr0.json
```

## Probar SLR(1)

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_ok.txt --method slr
```

Gramatica no LL(1) pero aceptada por SLR(1):

```bash
python yapar.py examples/slr_left_recursive.yalp -l examples/number_plus.yal --input examples/number_plus_input_ok.txt --method slr
```

Error sintactico:

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_error.txt --method slr
```

Conflicto SLR(1):

```bash
python yapar.py examples/slr_conflict.yalp --method slr
```

## Probar LALR(1)

Gramatica LR(1)/LALR(1) que no es SLR(1):

```bash
python3 yapar.py examples/lalr_not_slr.yalp --method slr
python3 yapar.py examples/lalr_not_slr.yalp -l examples/id_star_equal.yal --input examples/lalr_assignment_input_ok.txt --method lalr
```

Exportar la tabla/automata LALR:

```bash
python3 yapar.py examples/lalr_not_slr.yalp --method lalr --dot generated/lalr.dot --json generated/lalr.json
```

## Recuperacion de errores

```bash
python3 yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_error.txt --method slr --recover
```

## Arbol semantico

```bash
python3 yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_ok.txt --method slr --tree --tree-json generated/semantic_tree.json --tree-dot generated/semantic_tree.dot
```

## GUI tipo IDE

```bash
python3 yapar_ide.py
```

La GUI permite editar la gramatica, seleccionar lexer e input, ejecutar `ll1`, `lr0`, `slr` o `lalr`, activar `verbose`/`recover`, guardar salidas DOT/JSON y visualizar/exportar el arbol semantico.

## Frontend web

Desde la raiz del repo:

```bash
python3 yapar_web.py
```

Luego abra la URL que imprime la terminal, por ejemplo `http://127.0.0.1:5174`.

El frontend web permite cargar ejemplos, editar gramatica YAPar, lexer YALex e input, ejecutar `LL(1)`, `LR(0)`, `SLR` o `LALR`, ver resumen, tablas, automata, pasos del parser, consola y exportar JSON/DOT desde la misma pantalla.

Token usado pero no declarado:

```bash
python yapar.py examples/token_undeclared_error.yalp --method slr
```

## Pruebas

```bash
python3 -m unittest tests/test_ll1_preprocessing.py tests/test_yapar_algorithms.py
```

## Que funciona

- Lectura de `.yalp/.yapar` con `%token`, `IGNORE`, `%%` y producciones.
- Comentarios `/* ... */`.
- Validacion de tokens declarados, ignorados y usados.
- Integracion de tokens desde `.yal/.yalex` o lexers Python generados.
- Descarte de tokens `IGNORE` antes del parsing.
- EOF/`$` al final del stream.
- FIRST, FOLLOW y tabla LL(1).
- Parser predictivo LL(1).
- Deteccion de conflictos LL(1) y recursion izquierda.
- Gramatica aumentada `S' -> S`.
- Items, `closure`, `goto`, coleccion canonica y automata LR(0).
- Export DOT del automata LR(0).
- Tabla ACTION/GOTO SLR(1).
- Parser SLR(1) con shift/reduce/goto/accept.
- Deteccion de conflictos shift/reduce y reduce/reduce.
- Coleccion canonica LR(1), fusion de cores LR(0), tabla ACTION/GOTO y parser LALR(1).
- Deteccion de conflictos LALR shift/reduce y reduce/reduce.
- Recuperacion panic-mode opcional para LL(1), SLR(1) y LALR(1).
- GUI tipo IDE en `yapar_ide.py`.
- JSON de estructuras para interfaz.

## Pendientes conocidos

- No hay generacion de arbol AST semantico; el parser reporta aceptacion/rechazo y pasos.
- La recuperacion `--recover` es panic-mode: descarta tokens/estados para continuar, no reescribe la entrada ni garantiza multiples errores en todos los casos.

## Archivos principales tocados

- `Analizador Sintactico/yalp_parser.py`
- `Analizador Sintactico/token_stream.py`
- `Analizador Sintactico/ll1_analyzer.py`
- `Analizador Sintactico/lr0_automaton.py`
- `Analizador Sintactico/slr_parser.py`
- `Analizador Sintactico/lalr_parser.py`
- `Analizador Sintactico/yapar_runtime.py`
- `yapar.py`
- `yapar_ide.py`
- `yapar`
- `yapar_ll1.py`
- `examples/`
- `tests/`
- `docs/`

## Limitaciones conocidas

- Los nombres de tokens YAPar deben ser identificadores en mayusculas (`NUMBER`, `PLUS`, `TOKEN_NAME`). Algunos ejemplos antiguos de YALex emiten strings con espacios como `"MENOR QUE"`; esos nombres no son compatibles con YAPar sin normalizacion.
- Si YALex descarta whitespace con `return lexbuf`, YAPar puede declarar `WS` como `IGNORE`, pero el validador advertira que `WS` no es producido como token observable por el lexer.
- `make` no esta disponible en PATH en esta maquina; se verificaron comandos directos con `python`.
