# -*- coding: utf-8 -*-
"""Backend FastAPI de la app de matriculaciones de la DGT."""
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dgt

app = FastAPI(title="Matriculaciones DGT")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {value}")


def _norm(s):
    return " ".join(str(s).upper().split())


def _norm_list(values):
    """Normaliza una lista de valores (quita vacíos y normaliza)."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [_norm(v) for v in values if v and str(v).strip()]


def _filter_records(records, marcas=None, modelos=None, municipio=None, provincia=None,
                    cc_min=None, cc_max=None):
    marcas = _norm_list(marcas)
    modelos = _norm_list(modelos)
    if marcas:
        records = [r for r in records if _norm(r["marca"]) in marcas]
    if modelos:
        records = [r for r in records if _norm(r["modelo"]) in modelos]
    if municipio:
        municipio = _norm(municipio)
        records = [r for r in records if municipio in _norm(r["municipio"])]
    if provincia:
        provincia = _norm(provincia)
        records = [r for r in records if provincia in _norm(r["provincia"])]
    if cc_min is not None:
        records = [r for r in records if r["cc"] >= cc_min]
    if cc_max is not None:
        records = [r for r in records if r["cc"] <= cc_max]
    return records


@app.get("/")
def index():
    """Sirve el frontend."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "ok", "message": "Frontend no encontrado."}


@app.get("/api/months-available")
def months_available():
    """Meses (zips) presentes en local."""
    months = []
    for p in sorted(dgt.ZIPS_DIR.glob("export_mensual_mat_*.zip")):
        name = p.stem.replace("export_mensual_mat_", "")
        months.append({"ym": name, "year": int(name[0:4]), "month": int(name[4:6]),
                       "size": p.stat().st_size})
    return {"months": months}


@app.get("/api/status")
def status():
    """Estado: meses disponibles y meses cacheados en memoria."""
    return {
        "zips_dir": str(dgt.ZIPS_DIR),
        "zips": sorted(p.name for p in dgt.ZIPS_DIR.glob("*.zip")),
        "cached": dgt.cached_months(),
    }


@app.get("/api/facets")
def facets(start: str = Query(...), end: str = Query(...), marca: str | None = None):
    """Devuelve las marcas y modelos disponibles en el rango.

    - Si no se pasa `marca`: devuelve todas las marcas (con nº de unidades).
    - Si se pasa `marca`: devuelve los modelos de esa marca (con nº de unidades).
    """
    sd = _parse_date(start)
    ed = _parse_date(end)
    if sd > ed:
        raise HTTPException(status_code=400, detail="start debe ser <= end")

    # Asegurar que los datos estén disponibles
    dgt.ensure_months(sd, ed)
    records, _ = dgt.load_range(sd, ed)
    records = [r for r in records if sd <= date.fromisoformat(r["fecha"]) <= ed]

    if marca:
        marca_norm = _norm(marca)
        counts = {}
        for r in records:
            if _norm(r["marca"]) == marca_norm:
                key = r["modelo"]
                counts[key] = counts.get(key, 0) + 1
        items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return {"marca": marca, "modelos": [{"modelo": m, "unidades": c} for m, c in items]}

    counts = {}
    for r in records:
        counts[r["marca"]] = counts.get(r["marca"], 0) + 1
    items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {"marcas": [{"marca": m, "unidades": c} for m, c in items]}


@app.post("/api/ensure")
def ensure(start: str = Query(...), end: str = Query(...)):
    """Descarga los meses que falten entre dos fechas."""
    sd = _parse_date(start)
    ed = _parse_date(end)
    if sd > ed:
        raise HTTPException(status_code=400, detail="start debe ser <= end")
    results = dgt.ensure_months(sd, ed)
    return {
        "range": {"start": start, "end": end},
        "months": [{"ym": ym, "ok": ok, "error": err} for ym, ok, err in results],
        "all_ok": all(ok for _, ok, _ in results),
    }


class QueryPayload(BaseModel):
    start: str
    end: str
    marcas: list[str] | None = None
    modelos: list[str] | None = None
    municipio: str | None = None
    provincia: str | None = None
    cc_min: int | None = None
    cc_max: int | None = None


@app.post("/api/query")
def query(payload: QueryPayload):
    """Consulta: carga los datos del rango y aplica filtros.

    Devuelve:
      - summary: totales y unidades por mes
      - top_models: modelos más vendidos en el rango
      - details: los N registros (para búsquedas concretas)
    """
    sd = _parse_date(payload.start)
    ed = _parse_date(payload.end)
    if sd > ed:
        raise HTTPException(status_code=400, detail="start debe ser <= end")

    # Descargar automáticamente los meses que falten en el rango
    ensure_results = dgt.ensure_months(sd, ed)
    missing = [ym for ym, ok, _ in ensure_results if not ok]

    records, _ = dgt.load_range(sd, ed)
    # Filtrar por fecha exacta (día) dentro del rango
    records = [r for r in records if sd <= date.fromisoformat(r["fecha"]) <= ed]
    records = _filter_records(records, payload.marcas, payload.modelos,
                              payload.municipio, payload.provincia,
                              payload.cc_min, payload.cc_max)

    # Unidades por mes (dentro del rango)
    per_month = {}
    for r in records:
        m = r["fecha"][0:7]  # YYYY-MM
        per_month[m] = per_month.get(m, 0) + 1

    # Top modelos más vendidos (con datos técnicos relevantes)
    model_counts = {}
    model_specs = {}
    for r in records:
        key = (r["marca"], r["modelo"])
        model_counts[key] = model_counts.get(key, 0) + 1
        # Guardar especificaciones (modo = el valor más frecuente)
        spec = model_specs.setdefault(key, {})
        for f in ("cc", "peso", "par", "batalla"):
            val = r[f]
            if val:
                spec.setdefault(f, {}).setdefault(val, 0)
                spec[f][val] += 1

    top_models = []
    for (m, mo), c in sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:100]:
        spec = model_specs.get((m, mo), {})
        item = {"marca": m, "modelo": mo, "unidades": c}
        for f in ("cc", "peso", "par", "batalla"):
            counts = spec.get(f, {})
            if counts:
                item[f] = max(counts, key=counts.get)  # valor más frecuente
            else:
                item[f] = None
        top_models.append(item)

    # Distribución por marca (con % de diferencia respecto a la primera)
    marca_counts = {}
    for r in records:
        marca_counts[r["marca"]] = marca_counts.get(r["marca"], 0) + 1
    top_marcas_sorted = sorted(marca_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    top_marcas = []
    if top_marcas_sorted:
        first = top_marcas_sorted[0][1]
        for m, c in top_marcas_sorted:
            diff_pct = round((c / first - 1) * 100, 1) if first else 0
            top_marcas.append({"marca": m, "unidades": c, "diff_pct": diff_pct})

    return {
        "range": {"start": str(sd), "end": str(ed)},
        "missing": missing,
        "total": len(records),
        "per_month": per_month,
        "top_models": top_models,
        "top_marcas": top_marcas,
        "cached_months": dgt.cached_months(),
    }


# Servir el frontend estático
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)