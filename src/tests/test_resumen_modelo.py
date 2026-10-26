"""`make verify` resume el modelo guardado desde el contenedor (antes llamaba a python3 del host y fallaba en Windows sin Python)."""
import json

from app.config import settings
from scripts import resumen_modelo


def test_sin_modelo_dice_que_hay_que_entrenar(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "metrics_path", tmp_path / "metrics.json")
    assert resumen_modelo.linea() == "Sin modelo: make train"


def test_con_modelo_resume_version_f1_y_antifuga(tmp_path, monkeypatch):
    ruta = tmp_path / "metrics.json"
    ruta.write_text(json.dumps({"modelo_version": "v1", "f1_macro": 0.793, "cumple_umbrales": True,
                                "anti_fuga": {"superado": True}}), encoding="utf-8")
    monkeypatch.setattr(settings, "metrics_path", ruta)
    assert resumen_modelo.linea() == "v1 F1-macro 0.793 cumple True anti-fuga True"
