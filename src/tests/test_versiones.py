"""Coherencia de versiones: `docs/versiones.md` (la lista de referencia) frente a lo que fijan `requirements*.txt`, los
Dockerfile y el compose, y frente a lo instalado. Si cambias una versión en un sitio y no en el otro, falla.

Las pruebas que leen `docs/` y `environment/` se saltan cuando no están: en el contenedor del backend solo se monta
`src/`. Se ejecutan con `python -m pytest tests/test_versiones.py` desde `src/` en el equipo."""
import importlib.metadata as md
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOC = RAIZ / "docs" / "versiones.md"
REQUISITOS = [Path("src/requirements.txt"), Path("src/requirements-dev.txt"), Path("src/dashboard/requirements.txt")]
DOCKERFILES = [Path("environment/Dockerfile.backend"), Path("environment/Dockerfile.dashboard")]
COMPOSE = Path("environment/docker-compose.yml")

PIN = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]+\])?==([^\s#;]+)\s*(?:#.*)?$")

necesita_repo = pytest.mark.skipif(
    not (DOC.exists() and all((RAIZ / f).exists() for f in REQUISITOS + DOCKERFILES + [COMPOSE])),
    reason="solo en el repositorio completo (docs/ y environment/ no están en el contenedor del backend)")


def normalizar(nombre):
    return re.sub(r"[-_.]+", "-", nombre).lower()


def pines():
    """{paquete: {version: [ficheros]}} con todas las líneas `==` de los tres requirements."""
    salida = {}
    for fichero in REQUISITOS:
        for n, linea in enumerate((RAIZ / fichero).read_text(encoding="utf-8").splitlines(), 1):
            limpia = linea.strip()
            if not limpia or limpia.startswith(("#", "-r ")):
                continue
            m = PIN.match(limpia)
            assert m, f"{fichero}:{n}: «{limpia}» no es una versión fijada con `==`"
            salida.setdefault(normalizar(m.group(1)), {}).setdefault(m.group(2), []).append(fichero.as_posix())
    return salida


def seccion(numero):
    texto = DOC.read_text(encoding="utf-8")
    m = re.search(rf"^## {numero}\. .*?(?=^## |\Z)", texto, re.S | re.M)
    assert m, f"docs/versiones.md no tiene la sección {numero}"
    return m.group(0)


def filas(texto):
    """Filas de datos de las tablas Markdown de `texto`, como listas de celdas."""
    filas_ = []
    for linea in texto.splitlines():
        if linea.startswith("|") and not re.match(r"^\|[\s\-|:]+\|$", linea):
            filas_.append([c.strip() for c in linea.strip().strip("|").split("|")])
    return filas_[1:]  # la primera es la cabecera


def tabla_paquetes():
    """{paquete: (version, {ficheros})} de la sección 2 del documento."""
    salida = {}
    for celdas in filas(seccion(2)):
        paquete, version, ficheros = normalizar(celdas[0]), celdas[1], set(re.findall(r"`([^`]+)`", celdas[2]))
        assert paquete not in salida, f"docs/versiones.md repite {paquete} en la sección 2"
        salida[paquete] = (version, ficheros)
    return salida


@necesita_repo
def test_todo_esta_fijado_con_igual_y_un_paquete_tiene_una_sola_version():
    for paquete, versiones in pines().items():
        assert len(versiones) == 1, f"{paquete} está fijado con versiones distintas: {versiones}"


@necesita_repo
def test_la_lista_recoge_exactamente_los_paquetes_fijados_con_su_version_y_ficheros():
    reales = {p: (next(iter(v)), {f for fs in v.values() for f in fs}) for p, v in pines().items()}
    assert tabla_paquetes() == reales, (
        "docs/versiones.md (sección 2) no coincide con requirements*.txt: actualiza la lista a la vez que el fichero")


@necesita_repo
def test_las_imagenes_de_docker_son_las_de_la_lista():
    reales = set()
    for fichero in DOCKERFILES:
        reales |= set(re.findall(r"^FROM\s+(\S+)", (RAIZ / fichero).read_text(encoding="utf-8"), re.M))
    reales |= set(re.findall(r"^\s*image:\s*(\S+)", (RAIZ / COMPOSE).read_text(encoding="utf-8"), re.M))
    documentadas = {m for celdas in filas(seccion(3)) for m in re.findall(r"`([^`]+)`", celdas[1])}
    assert documentadas == reales, (
        f"imágenes distintas: solo en la lista {documentadas - reales}, solo en environment/ {reales - documentadas}")


@necesita_repo
def test_la_imagen_de_python_es_la_minima_que_declara_la_lista():
    minimo = re.search(r"\*\*Python mínimo: (\d+\.\d+)\*\*", DOC.read_text(encoding="utf-8"))
    assert minimo, "docs/versiones.md debe decir «**Python mínimo: X.Y**»"
    for fichero in DOCKERFILES:
        etiqueta = re.search(r"^FROM python:(\d+\.\d+)", (RAIZ / fichero).read_text(encoding="utf-8"), re.M)
        assert etiqueta and etiqueta.group(1) == minimo.group(1), (
            f"{fichero} usa python:{etiqueta and etiqueta.group(1)} y la lista declara {minimo.group(1)}")


@necesita_repo
def test_ningun_paquete_fijado_exige_mas_python_que_el_minimo_declarado():
    minimo = tuple(int(x) for x in re.search(r"\*\*Python mínimo: (\d+\.\d+)\*\*", DOC.read_text(encoding="utf-8"))[1].split("."))
    for paquete in pines():
        try:
            requiere = md.distribution(paquete).metadata.get("Requires-Python") or ""
        except md.PackageNotFoundError:
            continue
        m = re.search(r">=\s*(\d+)\.(\d+)", requiere)
        if m:
            assert (int(m[1]), int(m[2])) <= minimo, f"{paquete} exige Python {requiere} y el mínimo declarado es {minimo}"


@necesita_repo
def test_lo_instalado_coincide_con_lo_fijado():
    """Detecta un entorno desactualizado (p. ej. tras actualizar los requirements sin reinstalar). Los paquetes que no
    están instalados se saltan: el dashboard no se instala en el backend."""
    distintos = {}
    for paquete, versiones in pines().items():
        try:
            instalada = md.version(paquete)
        except md.PackageNotFoundError:
            continue
        if instalada != next(iter(versiones)):
            distintos[paquete] = f"instalada {instalada}, fijada {next(iter(versiones))}"
    assert not distintos, f"entorno distinto de requirements*.txt (reinstala y, si cambia scikit-learn, `make train`): {distintos}"
