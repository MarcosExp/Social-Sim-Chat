"""SOCIAL-SIM Chat — Dashboard del terapeuta (Streamlit).

Muestra el proceso de extremo a extremo y habla SOLO con la API del backend (ADR-003): no abre Postgres.
  1. Pipeline: estado de cada etapa (corpus -> sesiones -> clasificador -> predicciones).
  2. Alumno: trayectoria de las 5 métricas, etiqueta diseñada vs. predicha, alertas.
  3. Modelo: métricas, matriz de confusión, umbrales y comprobaciones anti-fuga.
  4. Conversación: turnos de una sesión sintética.
  5. Sesiones reales: métricas de conversaciones reales frente al corpus de entrenamiento.
  6. Consola del terapeuta: corregir la valoración de un turno, la etiqueta de la sesión y la nota clínica.

Datos SINTÉTICOS: validan la arquitectura, no la eficacia clínica.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # `cliente_api` junto a este fichero

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import cliente_api as api

st.set_page_config(page_title="SOCIAL-SIM Chat — Dashboard del terapeuta", layout="wide")

METRICAS = {
    "aMLU": "aMLU (longitud media de enunciado)",
    "latencia_pragmatica_ms": "Latencia pragmática (ms)",
    "IRC_pct": "IRC % (reciprocidad)",
    "PEPE": "PEPE (eficacia pragmática)",
    "pct_DET": "%DET (determinismo)",
}
COLORES = {"Progreso": "#2a9d8f", "Estancamiento": "#e9a820", "Regresión": "#d1495b"}


def df(datos) -> pd.DataFrame:
    return pd.DataFrame(datos or [])


ZONA = "Europe/Madrid"          # hora peninsular (Canarias va 1 h por detrás); la API y la BD guardan UTC


def hora_peninsular(serie: pd.Series) -> pd.Series:
    """Fechas UTC de la API -> texto en hora peninsular, p. ej. '18/10/2026 23:32:02'."""
    return pd.to_datetime(serie, utc=True).dt.tz_convert(ZONA).dt.strftime("%d/%m/%Y %H:%M:%S")


ETIQUETA_PANTALLA = {"progreso": "Progreso", "estancamiento": "Estancamiento", "regresion": "Regresión"}


def norm(e) -> str:
    """Etiqueta de la BD (minúsculas, sin tilde; ER v2) -> texto de pantalla. Las sesiones reales no tienen etiqueta de diseño."""
    if not isinstance(e, str) or not e:
        return "sin etiqueta (real)"
    base = e.split(" (")[0].strip()
    return ETIQUETA_PANTALLA.get(base.lower(), base)


st.title("SOCIAL-SIM Chat — dashboard del terapeuta")
st.caption("Datos sintéticos: el prototipo valida la arquitectura, no la eficacia clínica.")

try:
    resumen = api.leer("/resumen")
except api.ErrorAPI as exc:  # backend caído
    st.error(f"No se puede llegar a la API del backend: {exc}")
    st.stop()

tab_pipe, tab_alumno, tab_modelo, tab_conv, tab_real, tab_consola = st.tabs(
    ["Pipeline", "Alumno", "Modelo", "Conversación", "Sesiones reales", "Consola del terapeuta"])
metrics = api.leer("/modelo/metricas", opcional=True)

# ---------------------------------------------------------------- Pipeline
with tab_pipe:
    st.subheader("Estado de cada etapa")
    try:
        h = api.leer("/health")
    except api.ErrorAPI:
        h = {}
    etapas = [
        ("1 · Postgres + esquema", h.get("database") == "ok", h.get("database", "sin respuesta")),
        ("2 · Corpus cargado", resumen["sesiones_sinteticas"] > 0,
         f"{resumen['alumnos']} alumnos · {resumen['sesiones_sinteticas']} sesiones"),
        ("3 · Clasificador entrenado", metrics is not None,
         metrics["modelo_version"] if metrics else "ejecuta `make train`"),
        ("4 · Predicciones en BD", resumen["predicciones"] > 0, f"{resumen['predicciones']} filas"),
        ("5 · Backend FastAPI", h.get("status") == "ok", h.get("status", "sin respuesta")),
        ("6 · LLM local (Ollama)", h.get("llm") == "ok", h.get("llm", "sin respuesta")[:40]),
    ]
    cols = st.columns(len(etapas))
    for col, (nombre, ok, detalle) in zip(cols, etapas):
        col.metric(nombre, "OK" if ok else "Pendiente", detalle, delta_color="off")

    if resumen["sesiones_sinteticas"]:
        por_tray = pd.DataFrame({"trayectoria": [norm(k) for k in resumen["alumnos_por_trayectoria"]],
                                 "alumnos": list(resumen["alumnos_por_trayectoria"].values())})
        por_tray = por_tray.groupby("trayectoria", as_index=False).sum()
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(por_tray, x="trayectoria", y="alumnos", title="Alumnos por trayectoria diseñada"),
                        width="stretch")
        etq = pd.DataFrame({"etiqueta": [norm(k) for k in resumen["sesiones_sinteticas_por_etiqueta"]],
                            "sesiones": list(resumen["sesiones_sinteticas_por_etiqueta"].values())})
        etq = etq.groupby("etiqueta", as_index=False).sum()
        c2.plotly_chart(px.pie(etq, names="etiqueta", values="sesiones", color="etiqueta",
                               color_discrete_map=COLORES, title="Sesiones por etiqueta real"),
                        width="stretch")
    else:
        st.info("Base vacía. Ejecuta `make pipeline` (carga corpus + entrena clasificador).")

# ------------------------------------------------------------------ Alumno
with tab_alumno:
    alumnos = df(api.leer("/students"))
    if alumnos.empty:
        st.info("Sin alumnos. Ejecuta `make seed`.")
    else:
        sel = st.selectbox(
            "Alumno simulado", alumnos.student_id,
            format_func=lambda s: f"{s} — {alumnos.set_index('student_id').loc[s, 'trayectoria_disenada']}",
        )
        gate = api.leer(f"/students/{sel}/prediccion")
        if gate["disponible"]:
            st.success("Predicción disponible sobre las sesiones reales de este alumno.")
        else:
            with st.expander(f"Predicción sobre sesiones reales: no disponible "
                             f"({gate['sesiones_reales']} real(es) de {gate['ventana_requerida']} necesarias)"):
                for motivo in gate["motivos"]:
                    st.markdown(f"- {motivo}")
                st.caption("Las etiquetas predichas de la tabla corresponden al corpus sintético, calculadas por lotes con `make train`.")
        ses = df(api.leer(f"/sessions/by-student/{sel}"))
        pred = df(api.leer("/predicciones", student_id=sel))
        if ses.empty:
            st.info("Este alumno no tiene sesiones.")
            st.stop()
        for col in ("session_id", "etiqueta_predicha", "confianza", "es_estancamiento_operacional"):
            if col not in pred.columns:
                pred[col] = None
        ses = ses.merge(pred[["session_id", "etiqueta_predicha", "confianza", "es_estancamiento_operacional"]],
                        on="session_id", how="left")
        ses["real"] = ses["etiqueta_real_disenada"].map(norm)
        ses["etiqueta_predicha"] = ses["etiqueta_predicha"].map(lambda e: norm(e) if isinstance(e, str) else e)
        ses["corregida"] = ses["etiqueta_corregida"].map(lambda e: norm(e) if isinstance(e, str) else None)
        if ses["es_estancamiento_operacional"].fillna(False).astype(bool).any():
            st.warning("Alerta operacional: 3 sesiones consecutivas predichas como estancamiento.")
        fig = go.Figure()
        for col, nombre in METRICAS.items():
            v = ses[col].astype(float)
            rango = (v.max() - v.min()) or 1.0
            fig.add_trace(go.Scatter(x=ses.sesion_num, y=(v - v.min()) / rango, name=nombre, mode="lines+markers"))
        fig.update_layout(title="Evolución normalizada (0-1) de las 5 métricas", xaxis_title="Sesión",
                          yaxis_title="Escala relativa por métrica", height=380)
        st.plotly_chart(fig, width="stretch")
        tabla = ses[["sesion_num", "origen", "real", "etiqueta_predicha", "confianza", "es_estancamiento_operacional",
                     "corregida"]].rename(
            columns={"sesion_num": "sesión", "real": "etiqueta real (diseño)", "etiqueta_predicha": "predicha",
                     "es_estancamiento_operacional": "alerta", "corregida": "corregida (terapeuta)"}
        )
        st.dataframe(tabla, width="stretch", hide_index=True)
        st.caption("Valores crudos de las métricas")
        st.dataframe(ses[["sesion_num", *METRICAS.keys()]], width="stretch", hide_index=True)

# ------------------------------------------------------------------ Modelo
with tab_modelo:
    if metrics is None:
        st.info("Aún no hay modelo. Ejecuta `make train`.")
    else:
        m = metrics
        st.caption(f"Versión {m['modelo_version']} · {m['n_alumnos']} alumnos · {m['n_sesiones']} sesiones · "
                   "validación cruzada agrupada por alumno")
        c = st.columns(4)
        c[0].metric("F1-macro", m["f1_macro"], "cumple" if m["cumple_umbrales"]["f1_macro"] else "no cumple",
                    delta_color="normal" if m["cumple_umbrales"]["f1_macro"] else "inverse")
        c[1].metric("Accuracy", m["accuracy"])
        c[2].metric("Recall estancamiento", m["recall_estancamiento"],
                    "cumple" if m["cumple_umbrales"]["recall_estancamiento"] else "no cumple",
                    delta_color="normal" if m["cumple_umbrales"]["recall_estancamiento"] else "inverse")
        c[3].metric("Precisión estancamiento", m["precision_estancamiento"],
                    "cumple" if m["cumple_umbrales"]["precision_estancamiento"] else "no cumple",
                    delta_color="normal" if m["cumple_umbrales"]["precision_estancamiento"] else "inverse")
        st.caption("Umbrales: " + " · ".join(f"{k} ≥ {v}" for k, v in m["umbrales"].items()))

        mc = m["matriz_confusion"]
        st.plotly_chart(
            px.imshow(mc["valores"], x=mc["etiquetas"], y=mc["etiquetas"], text_auto=True,
                      labels=dict(x="Predicha", y="Real", color="Sesiones"), title="Matriz de confusión (out-of-fold)"),
            width="stretch",
        )
        h = m.get("heuristica")
        if h:
            st.caption(f"Heurística de referencia (pendiente de PEPE): F1-macro {h['f1_macro']} · "
                       f"recall estancamiento {h['recall_estancamiento']}. El modelo debe superarla.")
        d = m.get("deteccion")
        if d:
            st.subheader("Alerta temprana (3 sesiones seguidas sin progreso)")
            x = st.columns(4)
            x[0].metric("Retraso mediano (sesiones)", d["retraso_mediano"])
            x[1].metric("Alumnos detectados", f"{d['pct_alumnos_detectados']:.0%}")
            x[2].metric("Falsas alertas en progreso", f"{d['pct_falsa_alerta_progreso']:.0%}")
            x[3].metric("Sesiones evaluadas", m["n_sesiones"])
        if m.get("nota_sesiones"):
            st.caption(m["nota_sesiones"])
        af = m["anti_fuga"]
        st.subheader("Comprobaciones anti-fuga")
        a, b = st.columns(2)
        a.metric("F1 modelo señuelo (competencia + nº sesión)", af["f1_macro_senuelo_competencia_sesion"],
                 help="Debe quedar claramente por debajo del modelo real.")
        b.metric("F1 con etiquetas permutadas", af["f1_macro_etiquetas_permutadas"],
                 help="Debe rondar el azar.")
        if af["superado"]:
            st.success("Sin indicios de fuga de información.")
        else:
            st.error("El corpus filtra la etiqueta: el señuelo iguala o supera al modelo real. "
                     "Revisa el generador del corpus antes de fiarte de las métricas.")

# ------------------------------------------------------------ Conversación
with tab_conv:
    if resumen["sesiones_sinteticas"] == 0:
        st.info("Sin sesiones.")
    else:
        sid = st.selectbox("Alumno", df(api.leer("/students")).student_id, key="conv_alumno")
        sint_alumno = df(api.leer(f"/sessions/by-student/{sid}"))
        sint_alumno = sint_alumno[sint_alumno["origen"] == "sintetico"]
        nums = list(sint_alumno.sesion_num)
        if not nums:
            st.info("Este alumno no tiene sesiones sintéticas (solo reales): mira la pestaña «Sesiones reales».")
        else:
            n = st.select_slider("Sesión", options=nums)
            fila = sint_alumno[sint_alumno["sesion_num"] == n].iloc[0]
            cols = ["sesion_num", "competencia", "aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE", "pct_DET", "etiqueta_real_disenada"]
            st.dataframe(fila[[c for c in cols if c in fila.index]].astype(str).to_frame("valor"), width="stretch")   # mezcla texto y números: Arrow no la admite sin convertir
            st.info("Aquí se muestran las métricas por sesión. Los turnos sintéticos (`generar_turnos.py`) están en la base de datos, "
                    "pero este panel no los muestra. Los turnos de las sesiones reales están en la pestaña «Sesiones reales».")

# ----------------------------------------------------------- Sesiones reales
with tab_real:
    real = df(api.leer("/sessions", origen="real"))
    st.caption("Métricas calculadas desde conversaciones reales terminadas (no de prueba). Definiciones "
               "provisionales: docs/metricas-reales.md. NO hay etiqueta real: aquí se comprueba que las "
               "métricas caen en el rango con el que se entrenó el clasificador, no su acierto.")
    if real.empty:
        st.info("Aún no hay sesiones reales. Completa una conversación (POST /conversaciones, sin `prueba`).")
    else:
        real = real.sort_values("created_at", ascending=False)
        cols_real = ["student_id", "sesion_num", "competencia", "aMLU", "latencia_pragmatica_ms", "IRC_pct", "PEPE",
                     "pct_DET", "n_figuras", "n_turnos_evaluados", "n_turnos_amlu", "lpp_intento1", "lpp_intento2",
                     "definicion_version", "created_at"]
        vista = real[cols_real].copy()
        vista["created_at"] = hora_peninsular(vista["created_at"])
        st.dataframe(vista.rename(columns={"pct_DET": "pct_DET (provisional)", "aMLU": "aMLU (provisional: evaluador)",
                                           "PEPE": "PEPE (provisional: evaluador)", "IRC_pct": "IRC_pct (provisional: evaluador)",
                                           "created_at": "creada (hora peninsular)"}),
                     width="stretch", hide_index=True)
        st.warning("**aMLU, PEPE e IRC son provisionales** hasta validar el evaluador 0/1/2: el prompt cambió (p3, con guarda de "
                   "inyecciones) y aún no se ha validado con conversaciones reales ni con la batería 3 revisada por una persona; "
                   "las sesiones de abajo se valoraron con versiones anteriores (columna `evaluador_version` de cada turno; "
                   "informe de validación §10.6).")
        figs = real["n_figuras"].dropna().astype(int)
        if not figs.empty:
            saltos = sorted({round(100 / n) for n in figs if n})
            st.caption(f"**Granularidad:** {figs.min()}-{figs.max()} figuras por sesión (columna `n_figuras`): PEPE y %DET dan "
                       f"saltos de {saltos[0]}-{saltos[-1]} puntos de la escala (100 / nº de figuras); comparar con un "
                       "corpus continuo es sobre todo cualitativo.")
        st.caption("**%DET es provisional:** hoy es el % de turnos valorados con 2, no el determinismo RQA entre sesiones "
                   "del diseño (necesita varias sesiones por alumno). No es entrada del clasificador sobre sesiones reales.")
        with st.expander("Ver la conversación de una sesión real"):
            convs = real.set_index("conversacion_id")
            elegida = st.selectbox("Sesión", list(convs.index),
                                   format_func=lambda i: f"{convs.loc[i, 'student_id']} · sesión {convs.loc[i, 'sesion_num']}")
            detalle = api.leer(f"/conversaciones/{elegida}")
            st.dataframe(df(detalle["turnos"])[["orden", "rol", "nodo", "intento", "texto", "evaluacion", "accuracy_corregido",
                                                "rama", "latencia_ms", "llm_ms", "iniciativa"]],
                         width="stretch", hide_index=True)
            st.caption("Por figura (vista `turn_data` del ER: una fila por figura, no por intento):")
            st.dataframe(df(api.leer(f"/conversaciones/{elegida}/figuras")).drop(
                columns=["turn_id", "session_id", "conversacion_id", "texto_respuesta", "es_prueba"], errors="ignore"),
                width="stretch", hide_index=True)
        sint = df(api.leer("/sessions", origen="sintetico"))
        filas = []
        for col, nombre in METRICAS.items():
            if sint.empty:
                break
            s_, r_ = sint[col].astype(float), real[col].dropna().astype(float)
            if r_.empty or s_.empty:
                continue
            filas.append({"métrica": nombre + (" (provisional)" if col == "pct_DET" else " (provisional: evaluador)" if col in ("aMLU", "PEPE", "IRC_pct") else ""), "sintético p5": round(s_.quantile(.05), 2),
                          "sintético mediana": round(s_.median(), 2), "sintético p95": round(s_.quantile(.95), 2),
                          "n (sesiones con valor)": int(len(r_)), "real mediana": round(r_.median(), 2),
                          "% real fuera del rango sintético": round(100 * ((r_ < s_.min()) | (r_ > s_.max())).mean(), 1)})
        st.subheader("Real vs. corpus de entrenamiento")
        if filas:
            st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)
        else:
            st.info("Sin corpus sintético con el que comparar. Ejecuta `make seed`.")
        if len(real) < 20:
            st.caption(f"Con {len(real)} sesiones reales la comparación es orientativa (conviene ≥ 20).")

# ------------------------------------------------------- Consola del terapeuta
with tab_consola:
    st.caption("Correcciones del terapeuta. Pasan por la API: el valor original se conserva, las métricas de la sesión se "
               "recalculan con el valor efectivo (corregido si existe) y no se toca la BD desde aquí.")
    if st.session_state.get("aviso_consola"):
        st.success(st.session_state.pop("aviso_consola"))
    autor = st.text_input("Terapeuta (quién corrige)", key="consola_autor", max_chars=80,
                          help="Se guarda en el historial de correcciones. Es un nombre declarado, no verificado.").strip()
    reales = df(api.leer("/sessions", origen="real"))
    if reales.empty:
        st.info("Aún no hay sesiones reales que corregir.")
    else:
        reales = reales.sort_values("created_at", ascending=False).set_index("session_id")
        sesion_id = st.selectbox("Sesión real", list(reales.index), key="consola_sesion",
                                 format_func=lambda i: f"{reales.loc[i, 'student_id']} · sesión {reales.loc[i, 'sesion_num']} · "
                                                       f"{reales.loc[i, 'competencia']}")
        cid = reales.loc[sesion_id, "conversacion_id"]
        st.subheader("1 · Valoración de un turno")
        turnos = [t for t in api.leer(f"/conversaciones/{cid}")["turnos"] if t["rol"] == "menor" and t["evaluacion"] is not None]
        if not turnos:
            st.info("Esta conversación no tiene turnos valorados.")
        else:
            por_orden = {t["orden"]: t for t in turnos}
            orden = st.selectbox(
                "Turno del menor", list(por_orden), key="consola_turno",
                format_func=lambda o: f"{o} · {por_orden[o]['nodo']} (intento {por_orden[o]['intento']}) · "
                                      f"{por_orden[o]['texto'][:50]} · valoración {por_orden[o]['evaluacion']}"
                                      + (f" → corregida {por_orden[o]['accuracy_corregido']}" if por_orden[o]["accuracy_corregido"] is not None else ""))
            opciones = {"Dejar la del evaluador (quitar corrección)": None, "0 · literal o incorrecta": 0,
                        "1 · parcial": 1, "2 · correcta": 2}
            elegida = st.radio("Valoración correcta", list(opciones), key="consola_valor", horizontal=True)
            if st.button("Guardar corrección del turno", disabled=not autor):
                try:
                    r = api.patch(f"/conversaciones/{cid}/turnos/{orden}", {"accuracy_corregido": opciones[elegida]}, autor)
                    nueva = r["sesion"]
                    st.session_state["aviso_consola"] = (
                        f"Turno {orden} corregido. Métricas recalculadas: PEPE {nueva['PEPE']} · IRC % {nueva['IRC_pct']} · "
                        f"%DET {nueva['pct_DET']} · aMLU {nueva['aMLU']}.")
                    st.rerun()
                except api.ErrorAPI as exc:
                    st.error(f"No se pudo guardar: {exc}")
        st.subheader("2 · Etiqueta de la sesión y nota clínica")
        st.caption("La nota clínica es un dato sensible (RGPD): solo se muestra aquí, no en los listados de la API.")
        det = api.get(f"/sessions/{sesion_id}")
        etiquetas = {"Sin corrección": None, "Progreso": "progreso", "Estancamiento": "estancamiento", "Regresión": "regresion"}
        actual = next((k for k, v in etiquetas.items() if v == det["etiqueta_corregida"]), "Sin corrección")
        etq = st.selectbox("Etiqueta corregida", list(etiquetas), index=list(etiquetas).index(actual), key=f"consola_etq_{sesion_id}")
        nota = st.text_area("Nota clínica", value=det["nota_clinica"] or "", max_chars=2000, key=f"consola_nota_{sesion_id}")
        if st.button("Guardar etiqueta y nota", disabled=not autor):
            try:
                api.patch(f"/sessions/{sesion_id}/correccion", {"etiqueta_corregida": etiquetas[etq], "nota_clinica": nota.strip() or None}, autor)
                st.session_state["aviso_consola"] = "Etiqueta y nota guardadas."
                st.rerun()
            except api.ErrorAPI as exc:
                st.error(f"No se pudo guardar: {exc}")

        st.subheader("3 · Historial de correcciones de esta sesión")
        st.caption("Quién cambió qué y cuándo (**hora peninsular**, Europe/Madrid; Canarias va 1 h por detrás). "
                   "De la nota clínica solo consta que cambió, no su contenido.")
        log = api.get("/correcciones", session_id=sesion_id) + api.get("/correcciones", conversacion_id=cid)
        log = df(sorted({r["id"]: r for r in log}.values(), key=lambda r: r["id"], reverse=True))
        if log.empty:
            st.caption("Sin correcciones registradas.")
        else:
            log["fecha"] = hora_peninsular(log["fecha"])
            st.dataframe(log[["fecha", "autor", "tipo", "orden", "campo", "valor_anterior", "valor_nuevo"]]
                         .rename(columns={"fecha": "fecha (hora peninsular)"}), hide_index=True, width="stretch")
