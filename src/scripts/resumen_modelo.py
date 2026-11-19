"""Una línea con el modelo guardado, para `make verify`. Se ejecuta dentro del contenedor del backend: no hace falta Python en el host."""
import json

from app.config import settings


def linea() -> str:
    ruta = settings.metrics_path
    if not ruta.exists():
        return "Sin modelo: make train"
    m = json.loads(ruta.read_text(encoding="utf-8"))
    base = f"{m['modelo_version']} F1-macro {m['f1_macro']} cumple {m['cumple_umbrales']} anti-fuga {m['anti_fuga']['superado']}"
    criterios = m.get("criterios")
    if criterios is None:    # metrics.json de un entrenamiento anterior a NF4: solo tenía tres umbrales
        return base + " · criterios n/d (reentrena: make train)"
    fallan = [n for n, ok in criterios.items() if ok is False]
    sin_evaluar = [n for n, ok in criterios.items() if ok is None]
    extra = f" · criterios {m['criterios_cumplidos']}"
    if fallan:
        extra += f" · NO cumple: {'; '.join(fallan)}"
    if sin_evaluar:
        extra += f" · sin evaluar: {'; '.join(sin_evaluar)}"
    sv = m.get("servicio")
    if sv:    # modelo de servicio (sin %DET): el que predice sobre sesiones reales
        extra += f" · servicio {sv['modelo_version']} F1-macro {sv['f1_macro']} recall-estancamiento {sv['recall_estancamiento']}"
    return base + extra


if __name__ == "__main__":
    print(linea())
