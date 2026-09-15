# 🏍️ Matriculaciones DGT — Motos

Mini app local para consultar las matriculaciones de motos en España a partir de los
datos oficiales de la DGT.

## Qué hace

- **Descarga automática** de los zips mensuales de la DGT que falten en el rango de fechas consultado.
- **Parsea** solo los campos clave del TXT (fecha, marca, modelo, cilindrada, municipio, provincia).
- **Caché en memoria**: los datos ya cargados se mantienen en caliente, así cambiar filtros es instantáneo.
- **Visualización**: tabla de modelos más vendidos, ventas por mes, top marcas y comparación de modelos.

## Requisitos

- Python 3.10+
- Instalar dependencias:
  ```bash
  pip install -r requirements.txt
  ```

## Cómo ejecutar

```bash
python app.py
```

Abre en el navegador: **http://127.0.0.1:8000**

## Estructura

```
├── app.py              # Backend FastAPI
├── dgt.py              # Descarga, parseo y caché
├── static/index.html   # Frontend
├── data/zips/          # Zips descargados (persistencia)
└── requirements.txt
```

## Notas

- Los zips ya descargados se guardan en `data/zips/` y no se vuelven a bajar.
- Las motos se identifican por su categoría (L1, L3, L5, L7).
- El rango de fechas se consulta por mes: si pides un rango que cruza varios meses,
  se descargarán todos los zips necesarios.