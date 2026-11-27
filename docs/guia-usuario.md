# Guía de usuario

Para quien prepara una conversación (adulto), para el menor que juega y para el terapeuta que revisa los resultados. Cómo arrancar el sistema: [`README.md`](../README.md). Detalle técnico: [`guia-tecnica.md`](guia-tecnica.md).

> **Prototipo académico, sin validez clínica.** Los datos son sintéticos y las conversaciones «reales» son de prueba. **No usar con menores reales.** La herramienta apoya al terapeuta; no diagnostica ni sustituye su criterio.

## 1. Qué hace

- El menor practica con un personaje cuatro competencias del lenguaje: **metáforas, sarcasmo, deixis** y **preguntas recíprocas**.
- Cada respuesta se puntúa 0, 1 o 2 y, al terminar, se calculan cinco métricas de la sesión.
- El terapeuta revisa los resultados en un panel y puede corregir las puntuaciones.

## 2. Direcciones (con el sistema en marcha)

| Qué | Dirección | Quién |
|---|---|---|
| Chat | `http://localhost:8010/chat/` | Adulto y menor |
| Panel del terapeuta | `http://localhost:8501` | Terapeuta |
| Documentación de la API | `http://localhost:8010/docs` | Quien mantiene el sistema |

- El chat necesita un modelo de lenguaje funcionando (Ollama con `qwen3:14b`) o el modo simulado (`make up-simulado`).
- El panel no pide clave: la lleva configurada en `environment/.env`.
- Si se ha instalado con `make up`, ese fichero lo crea el propio sistema y también la clave.

## 3. Preparar una conversación (adulto)

La primera pantalla la rellena una persona adulta, no el menor.

1. Abre el chat.
2. **Alumno:** elige uno de la lista.
3. **Nombre que usará el personaje:** opcional (hasta 60 caracteres).
4. **Competencia:** déjala en «La del alumno» o elige una.
5. **Conversación de prueba:** marca la casilla si solo quieres ensayar; no guarda sesión ni métricas.
6. Pulsa **Empezar** y deja el equipo al menor.

- Si el límite semanal está activo y el alumno ya ha jugado sus veces, el chat lo dice y no deja empezar otra.
- Cualquier conversación **no marcada como prueba** genera datos reales del alumno; no lo uses para ensayar.

## 4. Cómo se juega (menor)

- El personaje (Mona, Nico o Teo, según la edad) saluda y pregunta si quiere jugar.
- Después le presenta frases, una a una. El menor escribe su respuesta en la caja y pulsa **Enviar** o la tecla Intro (Mayús + Intro hace un salto de línea). Máximo 500 caracteres.
- Si la respuesta no acierta, el personaje da una **ayuda** y hay **una segunda oportunidad**; después se pasa a la siguiente frase.
- El chat **nunca enseña la puntuación** al menor.
- Al terminar aparece «Hemos terminado por hoy». Un adulto puede empezar otra conversación con el botón.

**Ajustes de lectura** (arriba a la derecha, se recuerdan en ese navegador):

- **A− / A+:** tres tamaños de letra.
- **Alto contraste:** se activa solo si el sistema operativo lo pide.
- **Saltar al contenido:** enlace para teclado y lectores de pantalla (aparece con la tecla Tab).

## 5. Si algo falla en el chat

El chat muestra un aviso con lo que ha pasado. Si el aviso lo permite, el botón **Intentar otra vez** reenvía el mismo mensaje.

| El chat dice | Qué hacer |
|---|---|
| «El personaje no puede contestar ahora mismo» | Comprueba que Ollama está en marcha (o usa el modo simulado) y pulsa «Intentar otra vez» |
| «El personaje está atendiendo otra cosa» | Espera unos segundos y reintenta; el sistema atiende una petición a la vez |
| «Falta el modelo de lenguaje en el equipo» | Ejecuta `make pull-model` |
| «El juego no puede guardar tu respuesta ahora mismo» | La base de datos no responde: espera y reintenta; si sigue, `make health` |
| «No puedo leer lo que has escrito» | El menor debe reescribir la respuesta |
| «Algo ha fallado en el juego» / «La conversación se ha hecho demasiado larga» | Pide ayuda a quien mantiene el sistema (los avisos no reintentables lo indican) |
| «Ya has jugado todas las veces que tocaban esta semana» | El límite semanal está activo; vuelve otro día |

## 6. Panel del terapeuta

Seis pestañas:

| Pestaña | Para qué sirve |
|---|---|
| **Pipeline** | Estado de las seis etapas (base de datos, corpus, clasificador, predicciones, backend, LLM) y reparto del corpus |
| **Alumno** | Sesiones de un alumno con la etiqueta predicha y la alerta de no-progreso |
| **Modelo** | Métricas del clasificador frente a sus umbrales, el modelo de servicio (con su media de 10 semillas) y comprobaciones anti-fuga |
| **Conversación** | Métricas de una sesión sintética concreta |
| **Sesiones reales** | Métricas de las conversaciones reales terminadas |
| **Consola del terapeuta** | Corrección de puntuaciones, etiqueta y nota clínica, con historial |

**Cómo leer los datos (importante)**

- Las etiquetas predichas (progreso, estancamiento, regresión) del corpus sintético salen de validación cruzada. Sobre **sesiones reales** hay una predicción **orientativa**: aparece en la pestaña «Alumno» cuando el alumno tiene 4 sesiones reales en una misma competencia (las 3 primeras no se predicen). El modelo se entrenó solo con datos sintéticos, no usa %DET y las escalas reales pueden no coincidir: **no está validada con menores reales** y no sustituye el criterio del terapeuta. «fuera de rango» marca las métricas que el modelo no había visto.
- La **alerta** salta con 3 sesiones seguidas predichas como no-progreso. Las primeras sesiones de cada alumno salen como «datos insuficientes».
- En «Sesiones reales», **aMLU, PEPE e IRC son provisionales** (dependen de un evaluador aún sin validar con conversaciones reales) y **%DET es un proxy** pendiente de un experto.
- Cada sesión muestra el número de figuras (`n_figuras`): con 3–4 figuras, PEPE y %DET dan saltos de 25–33 puntos. Una sola sesión es ruidosa.
- Con menos de 20 sesiones reales la comparación con el corpus es orientativa.

**Corregir una puntuación (pestaña «Consola del terapeuta»)**

1. Escribe tu nombre en **Terapeuta (quién corrige)**. Se guarda en el historial, pero **no se verifica**.
2. Elige la sesión real y, en el apartado 1, el turno del menor y la valoración correcta (0, 1, 2 o quitar la corrección).
3. Pulsa **Guardar corrección del turno**. Las métricas de la sesión se recalculan y el valor original **se conserva**.
4. En el apartado 2 puedes poner una **etiqueta corregida** y una **nota clínica** (máximo 2.000 caracteres). La nota es un dato sensible: solo se ve en esta consola y **no está cifrada**.
5. El apartado 3 lista quién cambió qué y cuándo (hora peninsular). De la nota solo consta que cambió.

## 7. Lo que el sistema no hace

- No diagnostica, no detecta el trastorno y no sustituye al terapeuta.
- No está validado con menores ni con terapeutas: las cifras salen de datos sintéticos y baterías propias.
- No tiene usuarios ni roles: una clave compartida da acceso al panel.
- Su predicción sobre sesiones reales es orientativa y no está validada con menores.
- No registra los silencios del menor.

Lista completa de límites: [`README.md`](../README.md) y [`AUTORIA.md`](../AUTORIA.md).
