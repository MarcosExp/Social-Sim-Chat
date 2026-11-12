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
    # un metrics.json de antes de NF4 no trae los nueve criterios: lo dice, en lugar de callar
    assert resumen_modelo.linea() == "v1 F1-macro 0.793 cumple True anti-fuga True · criterios n/d (reentrena: make train)"


def _metrics(tmp_path, monkeypatch, criterios):
    ruta = tmp_path / "metrics.json"
    ruta.write_text(json.dumps({"modelo_version": "v2", "f1_macro": 0.8, "cumple_umbrales": True, "anti_fuga": {"superado": True},
                                "criterios": criterios,
                                "criterios_cumplidos": f"{sum(v is True for v in criterios.values())}/{len(criterios)}"}),
                    encoding="utf-8")
    monkeypatch.setattr(settings, "metrics_path", ruta)


def test_verify_muestra_los_nueve_criterios_y_nombra_los_que_fallan(tmp_path, monkeypatch):
    """B3 de la auditoría: `make verify` no comprobaba la ventaja sobre la heurística ni los tres criterios de detección."""
    _metrics(tmp_path, monkeypatch, {"f1_macro >= 0.75": True, "ventaja_f1_sobre_heuristica >= 0.05": False,
                                     "retraso_mediano <= 4": None})
    linea = resumen_modelo.linea()
    assert "criterios 1/3" in linea
    assert "NO cumple: ventaja_f1_sobre_heuristica >= 0.05" in linea
    assert "sin evaluar: retraso_mediano <= 4" in linea


def test_verify_con_todos_los_criterios_cumplidos_no_añade_avisos(tmp_path, monkeypatch):
    _metrics(tmp_path, monkeypatch, {"a": True, "b": True})
    linea = resumen_modelo.linea()
    assert linea.endswith("criterios 2/2") and "NO cumple" not in linea
