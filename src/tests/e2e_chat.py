#!/usr/bin/env python3
"""Prueba de extremo a extremo de la pantalla /chat con un navegador real (Playwright) contra la API simulada.

No la recoge pytest (el nombre no empieza por `test_`) porque necesita Playwright y un navegador:

    pip install playwright && playwright install chromium
    python -m tests.e2e_chat            # desde src/

Comprueba: el flujo completo, que la latencia se mide en el cliente, el reintento tras un 503 con el mismo texto y la misma
latencia, que un error no reintentable devuelve el texto al cuadro, el fin de la conversación y que no se muestra la valoración.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

PUERTO = 8099
BASE = f"http://127.0.0.1:{PUERTO}"
SRC = Path(__file__).resolve().parent.parent


def esperar_servidor():
    for _ in range(50):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=1).read()
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("La API simulada no arrancó")


def main() -> int:
    srv = subprocess.Popen([sys.executable, "-m", "scripts.mock_api_chat", "--puerto", str(PUERTO)], cwd=SRC)
    fallos: list[str] = []

    def comprobar(cond: bool, texto: str):
        print(("OK   " if cond else "FALLA"), texto)
        if not cond:
            fallos.append(texto)

    try:
        esperar_servidor()
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 900, "height": 900})
            pg.goto(BASE + "/chat/")
            pg.wait_for_selector("#alumno option[value='sim-001']", state="attached")
            comprobar(True, "la lista de alumnos carga desde GET /students")

            pg.click("#btn-empezar")
            comprobar("Elige un alumno" in pg.inner_text("#error-inicio"), "no empieza sin elegir alumno")
            pg.select_option("#alumno", "sim-001")
            pg.fill("#alias", "Álvaro")
            pg.click("#btn-empezar")
            pg.wait_for_selector("#mensajes .msg.bot")
            comprobar("Álvaro" in pg.inner_text("#mensajes"), "el personaje saluda con el alias")
            comprobar(pg.inner_text("#nombre-personaje") == "Mona", "se muestra el personaje")

            # turno 1: espera 700 ms antes de enviar -> la latencia del cliente debe ser >= 700
            time.sleep(0.7)
            pg.fill("#respuesta", "Bien, gracias")
            pg.click("#btn-enviar")
            pg.wait_for_function("document.querySelectorAll('#mensajes .msg.bot').length >= 3")
            ult = json.loads(urllib.request.urlopen(BASE + "/_debug/turnos").read())[-1]
            comprobar(ult["latencia_ms"] is not None and 700 <= ult["latencia_ms"] < 3000, f"latencia medida en el cliente ({ult['latencia_ms']} ms)")
            comprobar("evaluacion" not in pg.inner_text("body").lower() and "puntuación" not in pg.inner_text("body").lower(),
                      "no se muestra la valoración al menor")

            # turno 2: fallo 503 -> reintento con mismo texto y misma latencia
            time.sleep(0.4)
            pg.fill("#respuesta", "Quiere decir que es fácil fallo503")
            pg.click("#btn-enviar")
            pg.wait_for_selector("#bloque-error:not([hidden])")
            comprobar("otra vez" in pg.inner_text("#texto-error"), "503 reintentable: mensaje con opción de reintento")
            comprobar(pg.is_visible("#btn-reintentar"), "aparece el botón «Intentar otra vez»")
            pg.click("#btn-reintentar")
            pg.wait_for_function("document.querySelectorAll('#mensajes .msg.bot').length >= 5")
            envios = json.loads(urllib.request.urlopen(BASE + "/_debug/turnos").read())
            comprobar(envios[-1]["mensaje"].endswith("fallo503"), "el reintento reenvía el mismo texto")
            comprobar(envios[-1]["latencia_ms"] is not None and envios[-1]["latencia_ms"] >= 400, f"el reintento conserva la latencia original ({envios[-1]['latencia_ms']} ms)")
            comprobar(pg.locator("#mensajes .msg.pendiente").count() == 0, "no quedan mensajes pendientes tras el reintento")

            # turno 3: error no reintentable -> el texto vuelve al cuadro y no se deja como enviado
            n_menor = pg.locator("#mensajes .msg.menor").count()
            pg.fill("#respuesta", "fallo422 prueba")
            pg.click("#btn-enviar")
            pg.wait_for_selector("#bloque-error:not([hidden])")
            comprobar(pg.input_value("#respuesta") == "fallo422 prueba", "error no reintentable: el texto vuelve al cuadro")
            comprobar(pg.locator("#mensajes .msg.menor").count() == n_menor, "el mensaje fallido no se queda en la conversación")
            comprobar(not pg.is_visible("#btn-reintentar"), "sin botón de reintento si el error no es reintentable")

            # turnos 3 y 4 -> termina
            pg.fill("#respuesta", "Es muy fácil"); pg.click("#btn-enviar")
            pg.wait_for_function("document.querySelectorAll('#mensajes .msg.bot').length >= 7")
            pg.fill("#respuesta", "Se asustó mucho"); pg.click("#btn-enviar")
            pg.wait_for_selector("#fin:not([hidden])")
            comprobar(pg.is_disabled("#respuesta") or not pg.is_visible("#form-turno"), "al terminar se cierra el formulario")
            pg.screenshot(path=str(SRC / "tests" / "e2e_chat_fin.png"))

            # accesibilidad básica
            fuente = pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")
            comprobar(fuente >= 16, f"fuente base >= 16 px ({fuente})")
            comprobar(pg.get_attribute("#mensajes", "role") == "log", "la conversación es una región role=log")
            nav.close()
    finally:
        srv.terminate()
    print("\n" + ("TODO OK" if not fallos else f"{len(fallos)} FALLOS"))
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
