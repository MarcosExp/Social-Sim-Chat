/* SOCIAL-SIM Chat · pantalla de conversación del menor.
 * Vanilla JS, sin dependencias. Se sirve desde la propia API (/chat/) para no necesitar CORS.
 * Contrato: docs/api-conversacion.md (POST /conversaciones, POST /conversaciones/{id}/turnos).
 * La latencia (latencia_ms) se mide AQUÍ, en el cliente: desde que el último mensaje del personaje queda
 * visible hasta que el menor pulsa «Enviar». Así no incluye el tiempo del LLM (definición de la Fase 0).
 * Nunca se muestra al menor la valoración (evaluacion): solo la reacción del personaje.
 */
(function () {
  "use strict";
  const API = new URLSearchParams(location.search).get("api") || "";   // ?api=http://127.0.0.1:8010 en desarrollo
  const $ = (id) => document.getElementById(id);

  const MENSAJES_ERROR = {
    llm_no_disponible: "El personaje no puede contestar ahora mismo.",
    llm_ocupado: "El personaje está atendiendo otra cosa.",
    modelo_no_encontrado: "Falta el modelo de lenguaje en el equipo.",
    respuesta_invalida: "El personaje no ha entendido bien la respuesta.",
    contexto_excedido: "La conversación se ha hecho demasiado larga.",
    conversacion_terminada: "Esta conversación ya ha terminado.",
    conversacion_no_encontrada: "No encuentro esta conversación.",
  };

  let conv = null;                 // {id, personaje, estado}
  let tListo = null;               // performance.now() cuando el último mensaje del personaje quedó visible
  let pendiente = null;            // {texto, latencia} del turno que falló y puede reintentarse
  let enviando = false;

  /* ---------- utilidades ---------- */
  async function llamar(metodo, ruta, cuerpo) {
    let resp;
    try {
      resp = await fetch(API + ruta, {
        method: metodo,
        headers: cuerpo ? { "Content-Type": "application/json" } : undefined,
        body: cuerpo ? JSON.stringify(cuerpo) : undefined,
      });
    } catch (e) {
      throw { codigo: "sin_conexion", mensaje: "No hay conexión con el servidor.", reintentable: true };
    }
    let datos = null;
    try { datos = await resp.json(); } catch (e) { /* cuerpo vacío o no JSON */ }
    if (!resp.ok) {
      const d = datos && datos.codigo ? datos : (datos && datos.detail ? { codigo: "validacion", mensaje: JSON.stringify(datos.detail), reintentable: false } : null);
      throw d || { codigo: "http_" + resp.status, mensaje: "Error " + resp.status, reintentable: resp.status >= 500 };
    }
    return datos;
  }

  function mostrar(pantalla) {
    $("pantalla-inicio").hidden = pantalla !== "inicio";
    $("pantalla-chat").hidden = pantalla !== "chat";
  }

  function burbuja(rol, texto, clases) {
    const li = document.createElement("li");
    li.className = "msg " + rol + (clases ? " " + clases : "");
    const quien = document.createElement("span");
    quien.className = "quien";
    quien.textContent = rol === "bot" ? "💬 " + (conv ? conv.personaje : "Personaje") : "🧒 Tú";
    const cuerpo = document.createElement("span");
    cuerpo.textContent = texto;                 // textContent: nunca HTML
    li.append(quien, cuerpo);
    $("mensajes").append(li);
    li.scrollIntoView({ block: "nearest" });
    return li;
  }

  function mostrarTurnoBot(turnoBot) {
    for (const m of turnoBot.mensajes) burbuja("bot", m);
    tListo = performance.now();                 // empieza a contar la latencia del menor
  }

  function ponerEstado(texto) { $("estado").textContent = texto || ""; }

  function bloquear(b) {
    enviando = b;
    $("btn-enviar").disabled = b;
    $("respuesta").disabled = b;
  }

  function mostrarError(err, pendienteTurno) {
    const base = MENSAJES_ERROR[err.codigo] || err.mensaje || "Algo ha ido mal.";
    const adicional = err.reintentable ? " Puedes intentarlo otra vez." : " Pide ayuda a una persona adulta.";
    $("texto-error").textContent = "⚠ " + base + adicional;
    $("btn-reintentar").hidden = !(err.reintentable && pendienteTurno);
    $("bloque-error").hidden = false;
  }
  function ocultarError() { $("bloque-error").hidden = true; }

  function terminar() {
    $("form-turno").hidden = true;
    $("fin").hidden = false;
    ponerEstado("");
    $("btn-nueva").focus();
  }

  /* ---------- inicio ---------- */
  async function cargarAlumnos() {
    const sel = $("alumno");
    try {
      const alumnos = await llamar("GET", "/conversaciones/alumnos");
      sel.replaceChildren(new Option("Elige un alumno", ""));
      for (const a of alumnos) sel.append(new Option(a.student_id + " · " + a.competencia_objetivo, a.student_id));
    } catch (e) {
      sel.replaceChildren(new Option("No se pudo cargar la lista", ""));
      $("error-inicio").textContent = "⚠ " + (e.mensaje || "No se pudo cargar la lista de alumnos.");
      $("error-inicio").hidden = false;
    }
  }

  async function empezar(ev) {
    ev.preventDefault();
    $("error-inicio").hidden = true;
    const student_id = $("alumno").value;
    if (!student_id) { $("error-inicio").textContent = "⚠ Elige un alumno."; $("error-inicio").hidden = false; return; }
    const cuerpo = { student_id, prueba: $("prueba").checked };
    if ($("alias").value.trim()) cuerpo.alias = $("alias").value.trim();
    if ($("competencia").value) cuerpo.competencia = $("competencia").value;
    $("btn-empezar").disabled = true;
    try {
      const r = await llamar("POST", "/conversaciones", cuerpo);
      conv = { id: r.conversacion_id, personaje: r.personaje, estado: r.estado };
      $("mensajes").replaceChildren();
      $("nombre-personaje").textContent = r.personaje;
      $("etiqueta-competencia").textContent = r.competencia + (cuerpo.prueba ? " · prueba" : "");
      $("form-turno").hidden = false; $("fin").hidden = true; ocultarError(); pendiente = null;
      $("respuesta").value = ""; actualizarContador();
      mostrar("chat");
      mostrarTurnoBot(r.turno_bot);
      $("respuesta").focus();
    } catch (e) {
      $("error-inicio").textContent = "⚠ " + (MENSAJES_ERROR[e.codigo] || e.mensaje || "No se pudo empezar.");
      $("error-inicio").hidden = false;
    } finally {
      $("btn-empezar").disabled = false;
    }
  }

  /* ---------- turno ---------- */
  async function enviarTurno(texto, latencia, burbujaMenor) {
    bloquear(true);
    ocultarError();
    ponerEstado("💭 " + conv.personaje + " está pensando…");
    try {
      const r = await llamar("POST", "/conversaciones/" + conv.id + "/turnos", { mensaje: texto, latencia_ms: latencia });
      burbujaMenor.classList.remove("pendiente");
      pendiente = null;
      conv.estado = r.estado;
      ponerEstado("");
      mostrarTurnoBot(r.turno_bot);
      if (r.estado === "terminada") { terminar(); } else { bloquear(false); $("respuesta").focus(); }
    } catch (e) {
      ponerEstado("");
      if (e.codigo === "conversacion_terminada") { burbujaMenor.remove(); mostrarError(e, null); terminar(); return; }
      pendiente = e.reintentable ? { texto, latencia, burbuja: burbujaMenor } : null;
      if (!e.reintentable) burbujaMenor.remove();     // el servidor no guardó el turno; no lo dejamos como si hubiera contado
      mostrarError(e, pendiente);
      bloquear(false);
      $("respuesta").value = e.reintentable ? "" : texto;
      actualizarContador();
    }
  }

  function alEnviar(ev) {
    ev.preventDefault();
    if (enviando || !conv || conv.estado === "terminada") return;
    const texto = $("respuesta").value.trim();
    if (!texto) { ponerEstado("Escribe algo antes de enviar."); $("respuesta").focus(); return; }
    const latencia = tListo === null ? null : Math.max(0, Math.round(performance.now() - tListo));
    const b = burbuja("menor", texto, "pendiente");
    $("respuesta").value = ""; actualizarContador();
    enviarTurno(texto, latencia, b);
  }

  function reintentar() {
    if (!pendiente || enviando) return;
    const p = pendiente;
    enviarTurno(p.texto, p.latencia, p.burbuja);       // mismo texto y MISMA latencia: no se vuelve a medir
  }

  function actualizarContador() { $("contador").textContent = $("respuesta").value.length + " / 500"; }

  /* ---------- arranque ---------- */
  $("form-inicio").addEventListener("submit", empezar);
  $("form-turno").addEventListener("submit", alEnviar);
  $("btn-reintentar").addEventListener("click", reintentar);
  $("btn-nueva").addEventListener("click", () => { mostrar("inicio"); conv = null; $("alumno").focus(); });
  $("respuesta").addEventListener("input", actualizarContador);
  $("respuesta").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("form-turno").requestSubmit(); }
  });
  cargarAlumnos();
})();
