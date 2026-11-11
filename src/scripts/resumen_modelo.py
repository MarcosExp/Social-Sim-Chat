"""Una línea con el modelo guardado, para `make verify`. Se ejecuta dentro del contenedor del backend: no hace falta Python en el host."""
import json

from app.config import settings


def linea() -> str:
    ruta = settings.metrics_path
    if not ruta.exists():
        return "Sin modelo: make train"
    m = json.loads(ruta.read_text(encoding="utf-8"))
    return f"{m['modelo_version']} F1-macro {m['f1_macro']} cumple {m['cumple_umbrales']} anti-fuga {m['anti_fuga']['superado']}"


if __name__ == "__main__":
    print(linea())
