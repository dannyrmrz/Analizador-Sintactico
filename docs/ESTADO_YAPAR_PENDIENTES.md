# Estado actual de YAPar

## 1. Resumen del repo

El repositorio esta organizado en dos partes principales:

- `Analizador Lexico/`: generador estilo YALex escrito en Python. Contiene el CLI `yalexgen`/`yalex`, el codigo fuente en `src_py/`, ejemplos, pruebas de catedra y lexers ya generados.
- `Analizador Sintactico/`: avance de YAPar. Contiene el parser de archivos `.yalp/.yapar`, el preprocesamiento LL(1) y un modulo puente para convertir la salida textual del lexer generado en tokens.
- `examples/`: ejemplos minimos de gramaticas YAPar (`simple_parser.yalp` y `calculator_parser.yalp`).
- `tests/`: pruebas unitarias del preprocesamiento LL(1).
- `docs/`: documentacion de avance.
- `yapar_ll1.py`: CLI actual para parsear una gramatica YAPar y mostrar FIRST, FOLLOW y tabla LL(1).

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
- [ ] Gramatica aumentada: no existe todavia una estructura `S' -> S` para LR.
- [x] FIRST: implementado en `ll1_analyzer.py`.
- [x] FOLLOW: implementado en `ll1_analyzer.py`.
- [x] Tabla LL(1): implementada con deteccion de conflictos.
- [ ] Parser LL(1): falta consumir una secuencia de tokens y aceptar/rechazar entrada.
- [ ] Items LR(0): no implementado.
- [ ] Closure: no implementado para LR.
- [ ] Goto: no implementado para LR.
- [ ] Coleccion canonica LR(0): no implementada.
- [ ] Automata LR(0): no implementado.
- [ ] Tabla SLR(1): no implementada.
- [ ] Parser SLR(1): no implementado.
- [ ] LALR: no implementado.
- [~] Integracion con lexer: `token_stream.py` extrae tokens desde `.yal/.yalex` o desde un lexer Python generado, parsea salida real del lexer, filtra tokens ignorados y el CLI `yapar_ll1.py` ya acepta `-l/--lexer` para validar tokens YALex/YAPar. Todavia falta generar un parser final y consumir esos tokens con un parser LL(1), SLR(1) o LALR completo.

## 4. Faltantes detectados

- [x] Parser basico de archivos `.yalp/.yapar`.
- [x] Declaraciones `%token`.
- [x] Declaraciones `IGNORE`.
- [x] Producciones YAPar basicas.
- [x] FIRST/FOLLOW.
- [x] Tabla LL(1) y conflictos.
- [~] Puente de tokens YALex -> YAPar: ya valida tokens con `-l` y puede observar tokens de un lexer generado con `--input`; falta conectarlo a un parser sintactico ejecutable.
- [ ] Parser LL(1) ejecutable sobre tokens.
- [ ] Gramatica aumentada para familia LR.
- [ ] Items LR(0).
- [ ] `closure` LR(0).
- [ ] `goto` LR(0).
- [ ] Coleccion canonica LR(0).
- [ ] Exportacion/visualizacion de automata LR(0).
- [ ] Tabla SLR(1).
- [ ] Parser SLR(1).
- [ ] LALR.
- [ ] GUI tipo IDE.
- [ ] Reportes completos de errores sintacticos con recuperacion.

## 5. Plan tecnico de implementacion

1. Integrar tokens de YALex con YAPar.
   - [x] Agregar al CLI YAPar una opcion `-l/--lexer`.
   - [x] Leer tokens desde un `.yal/.yalex` o desde un lexer Python generado.
   - [x] Validar que los tokens usados/declarados por YAPar coincidan con los producidos por YALex.
   - [~] Reusar `Token`/`TokenStream` para no hardcodear tokens; falta que los parsers sintacticos consuman el stream.

2. Completar parser de `.yalp`.
   - Mantener el soporte actual de `%token`, `IGNORE`, `%%` y producciones.
   - Mejorar mensajes con linea/columna donde falte.
   - Definir la politica para `EOF`: tratarlo como token especial o como `$`.

3. Completar FIRST/FOLLOW.
   - Ya estan implementados; conviene agregar mas pruebas con epsilon, recursion y conflictos.

4. Terminar LL(1).
   - Implementar el parser predictivo con pila usando la tabla LL(1).
   - Consumir tokens reales de `TokenStream`.
   - Reportar errores sintacticos con token, lexema, linea y columna.

5. Implementar LR(0).
   - Crear producciones indexadas y gramatica aumentada.
   - Implementar items `A -> alpha . beta`.
   - Implementar `closure`, `goto` y coleccion canonica.
   - Exportar el automata LR(0) en texto y DOT.

6. Construir SLR(1) encima de LR(0) + FOLLOW.
   - Usar la coleccion LR(0) para acciones shift/reduce.
   - Usar FOLLOW para ubicar reducciones.
   - Detectar conflictos shift/reduce y reduce/reduce.
   - Implementar parser SLR(1).

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

Nota: `-o` queda aceptado por compatibilidad con la llamada esperada `yapar parser.yalp -l lexer.yal -o theparser`, pero este avance aun no emite el parser final.

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
