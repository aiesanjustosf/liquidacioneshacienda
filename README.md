# AIE - Liquidaciones de Hacienda (ARCA/LSP) - Streamlit

App para convertir PDFs de liquidaciones de hacienda (ARCA/LSP) a:

- Grilla de **Ventas** y **Compras** (con descarga a PDF)
- **Libro IVA Ventas** (Excel)
- **Gastos/Comisiones** (Excel)
- **Control Hacienda** (Excel) para Ventas y Compras: Tipo/Categoría, Cantidad, Kilos, Monto Neto (sin gastos)

## Ejecutar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Uso

1. Subí uno o varios PDFs.
2. Para cada PDF, elegí tu rol: **RECEPTOR** o **EMISOR**.
3. Presioná **Procesar**.
4. Descargá los archivos desde las pestañas.

## Assets (branding)

Colocá tus archivos en `assets/`:

- `assets/logo_aie.png`
- `assets/favicon-aie.ico`

Si no están, la app usa un fallback simple.

## Notas de negocio (resumen)

- El **Control Hacienda** toma el **monto neto sin gastos** como el **Importe Bruto** (base hacienda), sin IVA y sin gastos.
- Ajustes:
  - **Ajuste físico crédito**: resta cabezas/kilos/montos.
  - **Ajuste monetario/financiero crédito**: impacta sólo montos.
