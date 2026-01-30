import streamlit as st
import pandas as pd
import re
from pathlib import Path
from io import BytesIO
import tempfile

from src.parser import parse_pdf
from src.processor import build_outputs
from src.exporters import df_to_pdf_bytes, dfs_to_excel_bytes, df_to_template_excel_bytes

# --- Rutas de assets ---
HERE = Path(__file__).parent
LOGO = HERE / "aie-logo.png"
FAVICON = HERE / "aiefavicon.ico"

st.set_page_config(
    page_title="Liquidaciones de Hacienda (ARCA) → Compras / Ventas",
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
    st.markdown("## Liquidaciones de Hacienda (ARCA) → Compras / Ventas")
st.divider()


def _fmt_ar(x, decimals=2):
    try:
        v = float(x)
    except Exception:
        return x
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def style_df(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    money_pat = re.compile(r"(NETO|IVA|GASTO|IMPORTE|MONTO|BRUTO|TOTAL|PRECIO|COMISI|OTROS)", re.I)
    qty_pat = re.compile(r"(CABEZA|CANTIDAD)", re.I)
    kilos_pat = re.compile(r"KILO", re.I)

    fmt = {}
    for c in df.columns:
        if re.search(r"ALIC", str(c), re.I):
            fmt[c] = lambda v, _d=3: _fmt_ar(v, _d)
        elif money_pat.search(str(c)):
            fmt[c] = lambda v, _d=2: _fmt_ar(v, _d)
        elif kilos_pat.search(str(c)):
            fmt[c] = lambda v, _d=2: _fmt_ar(v, _d)
        elif qty_pat.search(str(c)):
            fmt[c] = lambda v, _d=0: _fmt_ar(v, _d)
    return df.style.format(fmt, na_rep="")



st.markdown("### 1) Subir comprobantes (PDF)")
col_u1, col_u2 = st.columns(2)
with col_u1:
    uploaded_emisor = st.file_uploader("Subir archivos como **EMISOR**", type=["pdf"], accept_multiple_files=True, key="up_emisor")
with col_u2:
    uploaded_receptor = st.file_uploader("Subir archivos como **RECEPTOR**", type=["pdf"], accept_multiple_files=True, key="up_receptor")


if "files_meta" not in st.session_state:
    st.session_state.files_meta = {}
if "parsed_docs" not in st.session_state:
    st.session_state.parsed_docs = {}

# Temp dir para persistir archivos subidos entre reruns
if "tmp_dir" not in st.session_state:
    st.session_state.tmp_dir = tempfile.mkdtemp(prefix="aie_hacienda_")
tmp_dir = Path(st.session_state.tmp_dir)
docs = []
roles = {}

def _parse_uploaded(files, role_label: str):
    if not files:
        return
    for uf in files:
        tmp_path = tmp_dir / uf.name
        tmp_path.write_bytes(uf.getbuffer())
        try:
            doc = parse_pdf(str(tmp_path))
            docs.append(doc)
            roles[doc.filename] = role_label
        except Exception as e:
            st.error(f"No pude leer {uf.name}: {e}")

_parse_uploaded(uploaded_emisor, "EMISOR")
_parse_uploaded(uploaded_receptor, "RECEPTOR")

if docs:
    st.markdown("### 2) Vista previa (rol asignado por subida)")
    for d in docs:
        role = roles.get(d.filename, "RECEPTOR")
        with st.expander(f"{d.filename} | {role} | Cód {d.cod_arca} {d.letra} {d.pv}-{d.numero} | {d.titulo}", expanded=False):
            colA, colB = st.columns([2, 8])
            with colA:
                st.write("**Soy:**", role)
                st.write("**Fecha:**", d.fecha or "-")
                st.write("**F. Operación:**", d.fecha_operacion or "-")
                if d.ajuste.es_ajuste:
                    st.warning(f"Ajuste detectado: {d.ajuste.tipo or ''} {d.ajuste.sentido or ''}")
            with colB:
                st.write("**Emisor:**", f"{d.emisor.nombre} (CUIT {d.emisor.cuit}) - {d.emisor.cond_iva}")
                st.write("**Receptor:**", f"{d.receptor.nombre} (CUIT {d.receptor.cuit}) - {d.receptor.cond_iva}")

    st.divider()
    if st.button("Procesar", type="primary"):
        st.session_state.parsed_docs = docs
        st.session_state.files_meta = roles
        st.success("Listo. Procesado.")


# Resultados
if st.session_state.parsed_docs:
    outputs = build_outputs(st.session_state.parsed_docs, st.session_state.files_meta)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Ventas", "Compras", "Gastos (detalle)", "Control Hacienda", "Descargas"])

    with tab1:
        st.subheader("Grilla de Ventas")
        dfv = outputs["ventas"]
        st.dataframe(style_df(dfv), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar PDF Ventas",
            data=df_to_pdf_bytes(dfv, title="Grilla de Ventas"),
            file_name="ventas.pdf",
            mime="application/pdf",
            disabled=dfv.empty,
        )
        # Libro ventas (Excel)
        st.subheader("Ventas - Excel")
        dflv = outputs["ventas_salida"]
        st.dataframe(dflv, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Ventas.xlsx",
            data=df_to_template_excel_bytes(str(HERE / 'templates' / 'emitidos_salida.xlsx'), dflv),
            file_name="ventas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dflv.empty,
        )

    with tab2:
        st.subheader("Grilla de Compras")
        dfc = outputs["compras"]
        st.dataframe(style_df(dfc), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar PDF Compras",
            data=df_to_pdf_bytes(dfc, title="Grilla de Compras"),
            file_name="compras.pdf",
            mime="application/pdf",
            disabled=dfc.empty,
        )


        # Compras/Gastos (Excel)
        st.subheader("Compras/Gastos - Excel")
        dfcg = outputs.get("compras_gastos_salida", pd.DataFrame())
        st.dataframe(style_df(dfcg), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Compras_Gastos.xlsx",
            data=df_to_template_excel_bytes(str(HERE / "templates" / "recibidos_salida.xlsx"), dfcg),
            file_name="compras_gastos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dfcg.empty,
        )
    with tab3:
        st.subheader("Gastos (detalle)")
        dfg = outputs["gastos"]
        st.dataframe(style_df(dfg), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Gastos_Detalle.xlsx",
            data=dfs_to_excel_bytes({"Detalle": dfg}),
            file_name="gastos_detalle.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dfg.empty,
        )

    with tab4:
        st.subheader("Control Hacienda - Ventas")
        dv_res = outputs["ctrl_ventas_resumen"]
        st.dataframe(style_df(dv_res), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar Control Hacienda Ventas.xlsx",
            data=dfs_to_excel_bytes({"Resumen": dv_res, "Detalle": outputs["ctrl_ventas_detalle"]}),
            file_name="control_hacienda_ventas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=dv_res.empty,
        )

        st.subheader("Control Hacienda - Compras")
        dc_res = outputs["ctrl_compras_resumen"]
        st.dataframe(style_df(dc_res), use_container_width=True, hide_index=True)
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
            "Ventas_Salida": outputs["ventas_salida"],
            "Compras_Gastos_Salida": outputs.get("compras_gastos_salida", pd.DataFrame()),
            "Ctrl_Ventas_Resumen": outputs["ctrl_ventas_resumen"],
            "Ctrl_Compras_Resumen": outputs["ctrl_compras_resumen"],
        }
        st.download_button(
            "Descargar TODO.xlsx",
            data=dfs_to_excel_bytes(sheets),
            file_name="hacienda_salidas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
st.markdown('---')
st.caption('Herramienta para uso interno | Developer Alfonso Alderete')
