# AIE - Liquidaciones de Hacienda (ARCA) - Streamlit

App para convertir PDFs de liquidaciones de hacienda (ARCA) a:

- Grilla de **Ventas** y **Compras** (con descarga a PDF)
- **Ventas (Emitidos Salida)** (Excel)
- **Gastos/Comisiones** (Excel)
- **Control Hacienda** (Excel) para Ventas y Compras: Tipo/Categoría, Cantidad, Kilos, Monto Neto (sin gastos)

## Ejecutar local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Uso

1. Subí PDFs en el panel correspondiente: **como EMISOR** o **como RECEPTOR**.
3. Presioná **Procesar**.
4. Descargá los archivos desde las pestañas.

## Assets (branding)

Colocá tus archivos en la raíz del repo:

- `aie-logo.png`
- `aiefavicon.ico`

Si no están, la app usa un fallback simple.

## Notas de negocio (resumen)

- El **Control Hacienda** toma el **monto neto sin gastos** como el **Importe Bruto** (base hacienda), sin IVA y sin gastos.
- Ajustes:
  - **Ajuste físico crédito**: resta cabezas/kilos/montos.
  - **Ajuste monetario/financiero crédito**: impacta sólo montos.
