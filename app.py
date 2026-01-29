import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
import tempfile

from src.parser import parse_pdf
from src.processor import build_outputs
from src.exporters import df_to_pdf_bytes, dfs_to_excel_bytes

# --- Rutas de assets ---
HERE = Path(__file__).parent
LOGO = HERE / "assets" / "logo_aie.png"
FAVICON = HERE / "assets" / "favicon-aie.ico"

st.set_page_config(
    page_title="Liquidaciones de Hacienda (ARCA/LSP) → AIE",
    page_icon=str(FAVICON) if FAVICON.exists() else "📄",
    layout="wide",
)

# Header
c1, c2 = st.columns([1, 6])
with c1:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    else:
        st.markdown("### AIE")
with c2:
    st.markdown("## Liquidaciones de Hacienda (ARCA/LSP) → Compras / Ventas")
    st.caption("Herramienta para uso interno | Developer Alfonso Alderete")

st.divider()

st.markdown("### 1) Subir comprobantes (PDF)")
uploaded = st.file_uploader("Seleccioná uno o varios PDFs", type=["pdf"], accept_multiple_files=True)

if "files_meta" not in st.session_state:
    st.session_state.files_meta = {}
if "parsed_docs" not in st.session_state:
    st.session_state.parsed_docs = []

tmp_dir = Path(tempfile.gettempdir()) / "aie_hacienda_uploads"
tmp_dir.mkdir(parents=True, exist_ok=True)

docs = []
roles = {}

if uploaded:
    st.markdown("### 2) Definir rol (EMISOR / RECEPTOR)")
    st.info("El mismo comprobante puede ser compra o venta según el rol. Seleccioná cómo figura tu parte en cada PDF.")
    for uf in uploaded:
        # Guardar a tmp
        tmp_path = tmp_dir / uf.name
        tmp_path.write_bytes(uf.getbuffer())
        # Parse preliminar
        try:
            doc = parse_pdf(str(tmp_path))
            docs.append(doc)
        except Exception as e:
            st.error(f"No pude leer {uf.name}: {e}")
            continue

    # UI roles
    for d in docs:
        with st.expander(f"{d.filename} | Cód {d.cod_arca} {d.letra} {d.pv}-{d.numero} | {d.titulo}", expanded=True):
            colA, colB, colC = st.columns([2,2,6])
            with colA:
                role = st.selectbox(
                    "Soy",
                    options=["RECEPTOR", "EMISOR"],
                    index=0,
                    key=f"role_{d.filename}",
                )
                roles[d.filename] = role
            with colB:
                st.write("**Fecha:**", d.fecha or "-")
                st.write("**F. Operación:**", d.fecha_operacion or "-")
            with colC:
                st.write("**Emisor:**", f"{d.emisor.nombre} (CUIT {d.emisor.cuit}) - {d.emisor.cond_iva}")
                st.write("**Receptor:**", f"{d.receptor.nombre} (CUIT {d.receptor.cuit}) - {d.receptor.cond_iva}")
                if d.ajuste.es_ajuste:
                    st.warning(f"Ajuste detectado: {d.ajuste.tipo or ''} {d.ajuste.sentido or ''}")

    st.divider()
    if st.button("Procesar", type="primary"):
        st.session_state.parsed_docs = docs
        st.session_state.files_meta = roles
        st.success("Listo. Procesado.")

# Resultados
if st.session_state.parsed_docs:
    outputs = build_outputs(st.session_state.parsed_docs, st.session_state.files_meta)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Ventas", "Compras", "Gastos", "Control Hacienda", "Descargas"])

    with tab1:
        st.subheader("Grilla de Ventas")
        dfv = outputs["ventas"]
        st.dataframe(dfv, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar PDF Ventas",
            data=df_to_pdf_bytes(dfv, title="Grilla de Ventas"),
            file_name="ventas.pdf",
            mime="application/pdf",
            disabled=dfv.empty,
        )
        # Libro ventas (Excel)
        st.subheader("Libro IVA Ventas (Excel)")
        dflv = outputs["libro_ventas"]
        st.dataframe(dflv, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Libro IVA Ventas.xlsx",
            data=dfs_to_excel_bytes({"Libro_Ventas": dflv}),
            file_name="libro_ventas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dflv.empty,
        )

    with tab2:
        st.subheader("Grilla de Compras")
        dfc = outputs["compras"]
        st.dataframe(dfc, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar PDF Compras",
            data=df_to_pdf_bytes(dfc, title="Grilla de Compras"),
            file_name="compras.pdf",
            mime="application/pdf",
            disabled=dfc.empty,
        )

    with tab3:
        st.subheader("Gastos / Comisiones (para planilla ND)")
        dfg = outputs["gastos"]
        st.dataframe(dfg, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Gastos.xlsx",
            data=dfs_to_excel_bytes({"Gastos": dfg}),
            file_name="gastos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dfg.empty,
        )

    with tab4:
        st.subheader("Control Hacienda - Ventas")
        dv_res = outputs["ctrl_ventas_resumen"]
        st.dataframe(dv_res, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Control Hacienda Ventas.xlsx",
            data=dfs_to_excel_bytes({"Resumen": dv_res, "Detalle": outputs["ctrl_ventas_detalle"]}),
            file_name="control_hacienda_ventas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dv_res.empty,
        )

        st.subheader("Control Hacienda - Compras")
        dc_res = outputs["ctrl_compras_resumen"]
        st.dataframe(dc_res, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Control Hacienda Compras.xlsx",
            data=dfs_to_excel_bytes({"Resumen": dc_res, "Detalle": outputs["ctrl_compras_detalle"]}),
            file_name="control_hacienda_compras.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dc_res.empty,
        )

    with tab5:
        st.subheader("Paquete completo")
        # Un solo Excel con todo
        sheets = {
            "Ventas": outputs["ventas"],
            "Compras": outputs["compras"],
            "Libro_Ventas": outputs["libro_ventas"],
            "Gastos": outputs["gastos"],
            "Ctrl_Ventas_Resumen": outputs["ctrl_ventas_resumen"],
            "Ctrl_Compras_Resumen": outputs["ctrl_compras_resumen"],
        }
        st.download_button(
            "Descargar TODO.xlsx",
            data=dfs_to_excel_bytes(sheets),
            file_name="hacienda_salidas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.caption("Nota: el 'Monto Neto (sin gastos)' del Control Hacienda se calcula como el Importe Bruto de la hacienda (base), excluyendo gastos/comisiones e IVA.")
