import json

from fastapi import Depends, APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.seguridad import exigir_terapeuta

router = APIRouter(prefix="/modelo", tags=["modelo"], dependencies=[Depends(exigir_terapeuta)])


@router.get("/metricas")
def metricas():
    """Resumen del último entrenamiento (F1, matriz de confusión, umbrales, comprobaciones anti-fuga)."""
    ruta = settings.metrics_path
    if not ruta.exists():
        return JSONResponse(status_code=404, content={
            "codigo": "modelo_no_entrenado", "mensaje": "Aún no hay modelo. Ejecuta `make train`.", "reintentable": False})
    return json.loads(ruta.read_text(encoding="utf-8"))
