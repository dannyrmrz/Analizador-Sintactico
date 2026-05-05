# Avance LL(1) y preprocesamiento YAPar/YALP

## Que se implemento

Este avance se enfoca en la etapa previa al parser LL(1). El sistema ya puede leer un archivo `.yalp` o `.yapar`, separar la seccion de tokens de la seccion de producciones, identificar terminales y no terminales, validar simbolos basicos, calcular FIRST y FOLLOW, construir la tabla LL(1) y reportar conflictos.

Todavia no se implementa el parser completo que acepta o rechaza cadenas de entrada. Esta parte prepara la informacion necesaria para hacerlo despues.

## Archivos tocados

- `Analizador Sintactico/yalp_parser.py`: parser de `.yalp/.yapar`, `%token`, `IGNORE`, producciones, validaciones y estructura canonica de gramatica.
- `Analizador Sintactico/ll1_analyzer.py`: calculo de FIRST, FOLLOW, tabla LL(1) y conflictos.
- `Analizador Sintactico/token_stream.py`: puente para tokens producidos por YALex, filtrado de tokens ignorados y validacion YAPar/YALex.
- `yapar_ll1.py`: comando de consola para ejecutar el avance.
- `examples/simple_parser.yalp`: gramatica LL(1) de expresiones.
- `tests/test_ll1_preprocessing.py`: pruebas minimas con `unittest`.

## Como se ejecuta

Desde la raiz del repositorio:

```bash
python yapar_ll1.py examples/simple_parser.yalp
```

Para correr las pruebas:

```bash
python -m unittest tests/test_ll1_preprocessing.py
```

## Entrada

El comando recibe un archivo `.yalp` o `.yapar` con este formato:

```yacc
%token NUMBER PLUS TIMES LPAREN RPAREN WS
IGNORE WS

%%

expr:
    term exprp
;
```

Se soportan comentarios `/* ... */`, varias lineas `%token`, una o varias entradas `IGNORE`, y producciones cerradas con `;`.

## Salida

La salida muestra:

- Archivo leido.
- Tokens declarados.
- Tokens ignorados.
- No terminales.
- Terminales.
- Simbolo inicial.
- Producciones.
- FIRST.
- FOLLOW.
- Tabla LL(1).
- Advertencias, errores o conflictos.

## Terminales

Los terminales son los tokens reales que vienen del lexer, por ejemplo `NUMBER`, `PLUS`, `TIMES`, `LPAREN` y `RPAREN`. En YAPar se declaran con `%token`.

## No terminales

Los no terminales son los nombres del lado izquierdo de las producciones, por ejemplo `expr`, `term` y `factor`. Se expanden usando reglas de la gramatica.

## FIRST

FIRST de un simbolo indica con que terminales puede iniciar una derivacion. Por ejemplo, si `expr` deriva a `term exprp`, y `term` puede iniciar con `NUMBER` o `LPAREN`, entonces `FIRST(expr) = { NUMBER, LPAREN }`.

## FOLLOW

FOLLOW de un no terminal indica que tokens pueden aparecer inmediatamente despues de ese no terminal en alguna derivacion. El simbolo inicial siempre tiene `$` en su FOLLOW.

## Tabla LL(1)

La tabla LL(1) cruza un no terminal con el token de entrada. Cada celda `M[A, a]` indica que produccion usar cuando el parser esta expandiendo `A` y mira el token `a`.

## Conflicto LL(1)

Hay conflicto LL(1) si una celda de la tabla recibe mas de una produccion. En ese caso la gramatica no es LL(1), porque con un solo token de mirada no se puede decidir que produccion aplicar.

## Validaciones incluidas

- Falta del separador `%%`.
- Producciones sin `;`.
- Lineas mal formadas en la seccion de tokens.
- Tokens usados en producciones pero no declarados con `%token`.
- No terminales usados pero no definidos.
- Tokens en `IGNORE` que no fueron declarados.
- Conflictos LL(1) en la tabla.

## Que falta para el proyecto final

- Integrar completamente los tokens generados por YALex.
- Consumir una cadena de tokens usando la tabla LL(1).
- Implementar el parser completo que acepta o rechaza cadenas.
- Implementar automata LR(0), SLR(1) y LALR.
- Mostrar tablas, automatas, resultados y errores en la GUI tipo IDE.

## Guion rápido para explicar al profesor

Para este avance nos enfocamos en la parte previa al parser LL(1). El sistema ya puede leer un archivo `.yalp`, separar la seccion de tokens y la seccion de producciones, identificar terminales y no terminales, calcular FIRST y FOLLOW, y con eso construir la tabla LL(1). Todavia no estamos ejecutando el parser completo sobre cadenas, pero esta parte es necesaria porque la tabla LL(1) es la base que luego permite decidir que produccion aplicar segun el no terminal actual y el token de entrada.

## Posibles preguntas del profesor

Pregunta: ¿Por qué FIRST es necesario?

Respuesta: Porque FIRST indica con que terminales puede iniciar una derivacion de un simbolo o produccion. Sirve para saber que produccion aplicar cuando el parser ve el siguiente token.

Pregunta: ¿Por qué FOLLOW es necesario?

Respuesta: Porque FOLLOW indica que tokens pueden aparecer despues de un no terminal. Es clave cuando una produccion puede derivar epsilon, ya que ayuda a llenar la tabla LL(1).

Pregunta: ¿Qué es la tabla LL(1)?

Respuesta: Es una tabla que cruza no terminales con tokens de entrada. Cada celda indica que produccion debe usarse. Si una celda tiene mas de una produccion, hay conflicto y la gramatica no es LL(1).

Pregunta: ¿Qué diferencia hay entre terminal y no terminal?

Respuesta: Los terminales son tokens reales que vienen del lexer, como `NUMBER` o `PLUS`. Los no terminales son variables de la gramatica, como `expr` o `term`, que se expanden usando producciones.

Pregunta: ¿Qué falta después de esto?

Respuesta: Falta consumir una cadena de tokens usando la tabla LL(1), implementar el parser completo, y luego avanzar con LR(0), SLR(1), LALR y la interfaz.

