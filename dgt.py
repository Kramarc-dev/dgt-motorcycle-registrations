# -*- coding: utf-8 -*-
"""Lógica central de la app de matriculaciones de la DGT.

- Descarga automática de los zips mensuales que falten.
- Parseo del TXT de ancho fijo extrayendo solo los campos clave.
- Caché en memoria de los datos ya cargados (los zips son la persistencia).
"""
import io
import os
import re
import zipfile
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ZIPS_DIR = BASE_DIR / "data" / "zips"

# URL patrón de la DGT: https://www.dgt.es/microdatos/salida/{YYYY}/{M}/vehiculos/matriculaciones/export_mensual_mat_{YYYYMM}.zip
DGT_URL = "https://www.dgt.es/microdatos/salida/{year}/{month}/vehiculos/matriculaciones/export_mensual_mat_{ym}.zip"

# ---------------------------------------------------------------------------
# Parseo del TXT de ancho fijo (714 caracteres por línea)
# ---------------------------------------------------------------------------
# Campos relevantes (índices 0-based, slice [start:end]):
#   fecha      [157:165] DDMMYYYY  (fecha de la operación/matriculación actual)
#   marca      [17:47]
#   modelo     [47:67]
#   cilindrada [95:99]  (cc)
#   peso       [108:111] (kg)
#   par        [114:117] (Nm)
#   batalla    [638:642] (mm)
#   municipio  [128:148]
#   provincia  [189:191]
#   categoria  [427:429]  (código de categoría, ej: "3E", "05", "1 " para coche)
FIELDS = {
    "fecha": (157, 165),
    "marca": (17, 47),
    "modelo": (47, 67),
    "cc": (95, 99),
    "peso": (108, 111),
    "par": (114, 117),
    "batalla": (638, 642),
    "municipio": (128, 148),
    "provincia": (189, 191),
    "categoria": (427, 429),
}

# Códigos de categoría que corresponden a motocicletas/ciclomotores.
#   - Códigos "XE" (1E, 3E, 4E, 5E, 6E, 7E): motos (L1, L3, L4, L5, L6, L7)
#   - Códigos "0X" (02, 04, 05, 06, 07, 08, 09): motos/ciclomotores (el carácter
#     de control * sustituye a la letra L)
MOTO_CODES = {"1E", "3E", "4E", "5E", "6E", "7E",
              "02", "04", "05", "06", "07", "08", "09"}


def _slice(line, name):
    start, end = FIELDS[name]
    return line[start:end].strip()


def parse_line(line):
    """Extrae los campos clave de una línea. Devuelve dict o None si no es moto."""
    if len(line) < 714:
        return None
    categoria = _slice(line, "categoria")
    # Solo motos: el código de categoría debe estar en MOTO_CODES
    if categoria not in MOTO_CODES:
        return None
    fecha = _slice(line, "fecha")
    try:
        day = int(fecha[0:2])
        month = int(fecha[2:4])
        year = int(fecha[4:8])
        fecha_iso = f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        return None
    cc_raw = _slice(line, "cc")
    try:
        cc = int(cc_raw)
    except ValueError:
        cc = 0

    # Peso (kg), par (Nm), batalla (mm) — pueden faltar
    def _num(name):
        try:
            return float(_slice(line, name))
        except ValueError:
            return 0

    return {
        "fecha": fecha_iso,
        "marca": _slice(line, "marca"),
        "modelo": _slice(line, "modelo"),
        "cc": cc,
        "peso": _num("peso"),
        "par": _num("par"),
        "batalla": _num("batalla"),
        "municipio": _slice(line, "municipio"),
        "provincia": _slice(line, "provincia"),
        "categoria": categoria,
    }


# ---------------------------------------------------------------------------
# Descarga y gestión de ficheros
# ---------------------------------------------------------------------------
def month_key(year, month):
    return f"{year:04d}{month:02d}"


def zip_path_for(ym):
    return ZIPS_DIR / f"export_mensual_mat_{ym}.zip"


def has_zip(ym):
    return zip_path_for(ym).exists()


def download_month(year, month):
    """Descarga el zip de un mes concreto. Devuelve la ruta o lanza excepción."""
    ym = month_key(year, month)
    dest = zip_path_for(ym)
    if dest.exists():
        return dest
    url = DGT_URL.format(year=year, month=month, ym=ym)
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def iter_months(start_date, end_date):
    """Genera los (year, month) entre dos fechas (inclusive)."""
    y, m = start_date.year, start_date.month
    while (y, m) <= (end_date.year, end_date.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def ensure_months(start_date, end_date):
    """Descarga todos los meses que falten en el rango. Devuelve lista de (ym, ok, error)."""
    results = []
    for y, m in iter_months(start_date, end_date):
        ym = month_key(y, m)
        if has_zip(ym):
            results.append((ym, True, None))
            continue
        try:
            download_month(y, m)
            results.append((ym, True, None))
        except Exception as e:  # noqa: BLE001
            results.append((ym, False, str(e)))
    return results


# ---------------------------------------------------------------------------
# Caché en memoria
# ---------------------------------------------------------------------------
# _cache[ym] = lista de dicts (registros de motos) ya parseados
_cache = {}


def load_month(ym):
    """Carga (y cachea) los registros de motos de un mes. Devuelve lista."""
    if ym in _cache:
        return _cache[ym]
    path = zip_path_for(ym)
    records = []
    if path.exists():
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith(".txt"):
                    continue
                text = z.read(name).decode("latin1")
                for line in text.splitlines():
                    rec = parse_line(line)
                    if rec:
                        records.append(rec)
    _cache[ym] = records
    return records


def load_range(start_date, end_date):
    """Carga todos los meses del rango y devuelve (registros, meses_faltantes)."""
    missing = [month_key(y, m) for y, m in iter_months(start_date, end_date)
               if not has_zip(month_key(y, m))]
    records = []
    for y, m in iter_months(start_date, end_date):
        records.extend(load_month(month_key(y, m)))
    return records, missing


def clear_cache():
    _cache.clear()


def cached_months():
    return sorted(_cache.keys())