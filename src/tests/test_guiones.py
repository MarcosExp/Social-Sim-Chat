from app.guiones import cargar_guiones


def test_guiones_validos_y_completos():
    g = cargar_guiones()
    assert {k: len(v.turnos) for k, v in g.competencias.items()} == {
        "Metáfora": 4, "Sarcasmo": 3, "Preguntas recíprocas": 3, "Deixis": 3}
    assert set(g.apertura) >= {"a1", "a2", "rama_2A", "rama_2B", "a3", "rama_3A", "rama_3B", "cierre"}
    for comp in g.competencias.values():
        for t in comp.turnos:
            assert t.frase and t.ayuda and t.correcta
        assert comp.cierre
