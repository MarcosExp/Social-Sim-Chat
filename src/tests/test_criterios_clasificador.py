"""NF4 (auditoría B2 y B3): `make train` usa los nueve criterios de `ml/evaluar_corpus.py` (Marcos), no una copia con límites propios."""
import re

from ml.evaluar_corpus import UMBRALES as CRITERIOS_MARCOS
from scripts import train_classifier as tc


def _res(**cambios):
    """Un resultado que cumple los nueve criterios (valores cercanos a los de la semilla 42)."""
    r = {"real": {"f1_macro": 0.797, "precision_estancamiento": 0.70, "recall_estancamiento": 0.725},
         "heuristica": {"f1_macro": 0.684}, "tramposo": {"f1_macro": 0.602}, "permutadas": {"f1_macro": 0.324},
         "deteccion": {"pct_alumnos_detectados": 0.968, "retraso_mediano": 3.0, "pct_falsa_alerta_progreso": 0.079}}
    for k, v in cambios.items():
        r[k] = {**r[k], **v} if isinstance(v, dict) and r[k] is not None else v
    return r


def test_son_nueve_criterios_y_los_de_marcos():
    c = tc.evaluar_criterios(_res())
    assert list(c) == [n for n, _ in CRITERIOS_MARCOS] and len(c) == 9
    assert all(v is True for v in c.values())


def test_los_tres_umbrales_propios_coinciden_con_los_tres_primeros_de_marcos():
    """Si alguien cambia un umbral en un sitio y no en el otro, este test lo dice (antes eran dos copias sin vigilar)."""
    de_marcos = {}
    for nombre, _ in CRITERIOS_MARCOS[:3]:
        m = re.fullmatch(r"(\w+) >= ([0-9.]+)", nombre)
        de_marcos[m.group(1).replace("precision", "precision").replace("recall", "recall")] = float(m.group(2))
    assert tc.UMBRALES == {"f1_macro": de_marcos["f1_macro"], "recall_estancamiento": de_marcos["recall_estancamiento"],
                           "precision_estancamiento": de_marcos["precision_estancamiento"]}


def test_B2_las_etiquetas_permutadas_usan_el_limite_de_marcos_0_40_no_0_45():
    """Antes `anti_fuga.superado` aceptaba 0,42 (< 0,45) aunque `evaluar_corpus.py` lo rechaza (> 0,40)."""
    c = tc.evaluar_criterios(_res(permutadas={"f1_macro": 0.42}))
    assert c[tc.NOMBRE_PERMUTADAS] is False
    assert tc.evaluar_criterios(_res(permutadas={"f1_macro": 0.40}))[tc.NOMBRE_PERMUTADAS] is True


def test_B3_se_comprueban_la_ventaja_sobre_la_heuristica_y_los_tres_de_deteccion():
    assert tc.evaluar_criterios(_res(heuristica={"f1_macro": 0.78}))["ventaja_f1_sobre_heuristica >= 0.05"] is False
    d = tc.evaluar_criterios(_res(deteccion={"pct_alumnos_detectados": 0.80, "retraso_mediano": 6.0,
                                              "pct_falsa_alerta_progreso": 0.30}))
    assert d["alumnos_detectados >= 0.90"] is False
    assert d["retraso_mediano <= 4"] is False
    assert d["falsas_alertas_progreso <= 0.15"] is False


def test_un_corpus_sin_deteccion_deja_esos_criterios_sin_evaluar_en_lugar_de_dar_falso():
    c = tc.evaluar_criterios(_res(deteccion=None))
    assert [n for n, v in c.items() if v is None] == ["alumnos_detectados >= 0.90", "retraso_mediano <= 4",
                                                     "falsas_alertas_progreso <= 0.15"]
    assert sum(v is True for v in c.values()) == 6
