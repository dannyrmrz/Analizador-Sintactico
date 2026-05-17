# Estado actual de YAPar

## 1. Resumen del repo

El repositorio esta organizado en dos partes principales:

- `Analizador Lexico/`: generador estilo YALex escrito en Python. Contiene el CLI `yalexgen`/`yalex`, el codigo fuente en `src_py/`, ejemplos, pruebas de catedra y lexers ya generados.
- `Analizador Sintactico/`: YAPar. Contiene el parser de archivos `.yalp/.yapar`, LL(1), LR(0), SLR(1), base documentada LALR y modulos puente para consumir tokens de YALex.
- `examples/`: ejemplos minimos de gramaticas YAPar (`simple_parser.yalp` y `calculator_parser.yalp`).
- `tests/`: pruebas unitarias del preprocesamiento LL(1).
- `docs/`: documentacion de avance.
- `yapar_ll1.py`: CLI actual para parsear una gramatica YAPar y mostrar FIRST, FOLLOW y tabla LL(1).
- `yapar.py` / `yapar`: CLI principal para ejecutar YAPar con `--method ll1|lr0|slr|lalr`.

El proyecto esta implementado en Python. No hay codigo C/C11 en el repo.

Rama de trabajo actual detectada: `feature/avance-yapar-ll1-preprocessing`.
Rama sugerida para continuar el proyecto completo: `feature/yapar-ll1-lr0-slr-integration`.

## 2. Estado de YALex

- [x] Lectura de `.yal` / `.yalex`: `Analizador Lexico/src_py/main.py` lee la especificacion recibida por CLI.
- [x] Parser de reglas lexicas: `yal_spec.py` parsea `header`, `let`, `rule`, acciones y `trailer`.
- [x] Construccion de regex / AST: `regex_parse.py`, `ast.py` y `charset.py` construyen AST de expresiones regulares con `let`, literales, sets, wildcard, diferencia, concatenacion, alternancia y operadores unarios.
- [x] NFA: `nfa.py` construye automatas no deterministas desde el AST.
- [x] DFA: `dfa.py` implementa subconjuntos, transiciones y seleccion de aceptacion.
- [x] Generacion de lexer: `emit.py` genera un lexer Python ejecutable.
- [x] Salida de tokens: el lexer generado imprime lineas `TOKEN <TYPE> "<lexeme>" (line L, col C)`.
- [x] Manejo de errores lexicos: el lexer generado imprime `LEXICAL_ERROR line L col C: "<byte>"`.
- [x] Linea y columna: el lexer generado mantiene `line` y `col` para tokens y errores.
- [~] Compatibilidad exacta con todos los dialectos YALex: el README indica que las pruebas de catedra fueron adaptadas al dialecto soportado por este `yalexgen`.

## 3. Estado de YAPar

- [x] Lectura de `.yalp` / `.yapar`: `yalp_parser.py` expone `parse_yalp_file`.
- [x] Parser de `%token`: soporta una o varias declaraciones y multiples tokens por linea.
- [x] Parser de `IGNORE`: soporta una o varias lineas `IGNORE`.
- [x] Parser de producciones: soporta `lhs: ... | ... ;` despues de `%%`.
- [x] Validacion de terminales y no terminales: detecta tokens no declarados, no terminales no definidos, duplicados y tokens ignorados no declarados.
- [x] Gramatica aumentada: `lr0_automaton.py` crea `S' -> S` para LR.
- [x] FIRST: implementado en `ll1_analyzer.py`.
- [x] FOLLOW: implementado en `ll1_analyzer.py`.
- [x] Tabla LL(1): implementada con deteccion de conflictos.
- [x] Parser LL(1): `LL1Analyzer.parse(...)` consume `TokenStream`/tokens y acepta o rechaza.
- [x] Items LR(0): implementados como `LR0Item`.
- [x] Closure: implementado en `LR0Automaton.closure`.
- [x] Goto: implementado en `LR0Automaton.goto`.
- [x] Coleccion canonica LR(0): implementada con BFS.
- [x] Automata LR(0): implementado y exportable a DOT.
- [x] Tabla SLR(1): implementada en `SLRParser`.
- [x] Parser SLR(1): implementado con stack de estados.
- [~] LALR: existe base documentada en `lalr_parser.py`, pero no esta completo.
- [x] Integracion con lexer: `token_stream.py` extrae tokens desde `.yal/.yalex` o desde un lexer Python generado, parsea salida real del lexer, filtra tokens ignorados y el CLI principal puede ejecutar LL(1)/SLR con tokens reales.

## 4. Faltantes detectados

- [x] Parser basico de archivos `.yalp/.yapar`.
- [x] Declaraciones `%token`.
- [x] Declaraciones `IGNORE`.
- [x] Producciones YAPar basicas.
- [x] FIRST/FOLLOW.
- [x] Tabla LL(1) y conflictos.
- [x] Puente de tokens YALex -> YAPar.
- [x] Parser LL(1) ejecutable sobre tokens.
- [x] Gramatica aumentada para familia LR.
- [x] Items LR(0).
- [x] `closure` LR(0).
- [x] `goto` LR(0).
- [x] Coleccion canonica LR(0).
- [x] Exportacion/visualizacion de automata LR(0) en DOT.
- [x] Tabla SLR(1).
- [x] Parser SLR(1).
- [~] LALR: base limpia y documentada; falta algoritmo LR(1)+merge.
- [ ] GUI tipo IDE.
- [~] Reportes completos de errores sintacticos: ya incluyen token, linea, columna y esperados; no hay recuperacion avanzada.

## 5. Plan tecnico de implementacion

1. Integrar tokens de YALex con YAPar.
   - [x] Agregar al CLI YAPar una opcion `-l/--lexer`.
   - [x] Leer tokens desde un `.yal/.yalex` o desde un lexer Python generado.
   - [x] Validar que los tokens usados/declarados por YAPar coincidan con los producidos por YALex.
   - [x] Reusar `Token`/`TokenStream` para no hardcodear tokens.

2. Completar parser de `.yalp`.
   - Mantener el soporte actual de `%token`, `IGNORE`, `%%` y producciones.
   - Mejorar mensajes con linea/columna donde falte.
   - Definir la politica para `EOF`: tratarlo como token especial o como `$`.

3. Completar FIRST/FOLLOW.
   - Ya estan implementados; conviene agregar mas pruebas con epsilon, recursion y conflictos.

4. Terminar LL(1).
   - [x] Implementar el parser predictivo con pila usando la tabla LL(1).
   - [x] Consumir tokens reales de `TokenStream`.
   - [x] Reportar errores sintacticos con token, lexema, linea y columna.

5. Implementar LR(0).
   - [x] Crear producciones indexadas y gramatica aumentada.
   - [x] Implementar items `A -> alpha . beta`.
   - [x] Implementar `closure`, `goto` y coleccion canonica.
   - [x] Exportar el automata LR(0) en texto y DOT.

6. Construir SLR(1) encima de LR(0) + FOLLOW.
   - [x] Usar la coleccion LR(0) para acciones shift/reduce.
   - [x] Usar FOLLOW para ubicar reducciones.
   - [x] Detectar conflictos shift/reduce y reduce/reduce.
   - [x] Implementar parser SLR(1).

7. Preparar LALR si no alcanza tiempo.
   - Reusar la base LR.
   - Definir estructura para items LR(1) con lookahead.
   - Fusionar estados con mismo core LR(0).
   - Documentar si queda como pendiente tecnico.

8. Agregar pruebas.
   - Pruebas de parser `.yalp`.
   - Pruebas de FIRST/FOLLOW y tabla LL(1).
   - Pruebas de integracion YALex -> YAPar.
   - Pruebas de LR(0)/SLR(1) con gramaticas pequenas.

9. Documentar comandos.
   - Mantener comandos reproducibles en `docs/`.
   - Actualizar scripts/Makefile si se agrega un CLI oficial `yapar`.

## 6. Comandos para probar

Desde la raiz del repo:

```bash
python yapar_ll1.py examples/simple_parser.yalp
```

Validar una gramatica YAPar contra una especificacion YALex:

```bash
python yapar_ll1.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal"
```

Validar contra un lexer Python generado y observar tokens de una entrada:

```bash
python yapar_ll1.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/lexer_generated.py" --input "Analizador Lexico/examples/input_ok.txt" -o theparser
```

Nota: `yapar_ll1.py` conserva `-o` como salida informativa. El CLI principal `yapar.py` si puede emitir un runner ejecutable con `-o`.

CLI principal SLR(1) con lexer YALex y entrada:

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" --input examples/calculator_input_ok.txt --method slr --dot generated/lr0_automaton.dot
```

Generar un runner de parser y ejecutarlo:

```bash
python yapar.py examples/calculator_parser.yalp -l "Analizador Lexico/examples/calculator.yal" -o generated/theparser.py --method slr
python generated/theparser.py examples/calculator_input_ok.txt
```

Probar una gramatica no LL(1) pero SLR(1):

```bash
python yapar.py examples/slr_left_recursive.yalp -l examples/number_plus.yal --input examples/number_plus_input_ok.txt --method slr
```

Probar conflicto SLR(1):

```bash
python yapar.py examples/slr_conflict.yalp --method slr
```

Pruebas unitarias actuales:

```bash
python -m unittest tests/test_ll1_preprocessing.py
```

Desde `Analizador Lexico/`, generar y ejecutar el lexer de calculadora:

```bash
python yalexgen examples/calculator.yal -o examples/lexer_generated.py --dot examples/regex_tree.dot --no-png
python examples/lexer_generated.py examples/input_ok.txt
```

Tambien existe un `Makefile` dentro de `Analizador Lexico/` con targets como `example`, `example-error`, `example-features`, `verify` y `test-catedra`, pero en esta maquina `make` no esta disponible en PATH. Los comandos Python directos anteriores si fueron verificados.
