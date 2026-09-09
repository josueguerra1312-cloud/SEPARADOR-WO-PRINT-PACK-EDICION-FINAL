from __future__ import annotations

import hashlib
import hmac
import io
import time
import tomllib
import zipfile
from pathlib import Path

import streamlit as st

from pdf_editor_engine import create_zip as create_editor_zip
from pdf_editor_engine import edit_pdf
from pdf_separator import build_zip as create_separator_zip
from pdf_separator import separate_pdf

AUTH_VERSION = "separador-editor-v1"
USERS_FILE = Path(__file__).with_name("users.toml")


def require_login() -> None:
    if st.session_state.get("authenticated") and st.session_state.get("auth_version") == AUTH_VERSION:
        with st.sidebar:
            st.write(f"Usuario: **{st.session_state['username']}**")
            st.caption(f"Rol: {st.session_state.get('role', 'usuario')}")
            if st.button("Cerrar sesion", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        return

    st.session_state["authenticated"] = False
    st.title("Acceso al separador y editor PDF")
    locked = int(float(st.session_state.get("locked_until", 0)) - time.time())
    if locked > 0:
        st.error(f"Acceso bloqueado. Intenta nuevamente en {locked} segundos.")
        st.stop()

    with st.form("login_integrado"):
        username = st.text_input("Usuario")
        password = st.text_input("Contrasena", type="password")
        submitted = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

    if submitted:
        if not USERS_FILE.exists():
            st.error("No se encontro users.toml en la raiz del repositorio.")
            st.stop()
        with USERS_FILE.open("rb") as fh:
            users = tomllib.load(fh).get("users", {})
        user = users.get(username.strip())
        valid = False
        if user:
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                bytes.fromhex(user["salt"]),
                int(user["iterations"]),
            ).hex()
            valid = hmac.compare_digest(actual, user["password_hash"])
        if valid:
            st.session_state.update(
                authenticated=True,
                auth_version=AUTH_VERSION,
                username=username.strip(),
                role=user.get("role", "usuario"),
                login_attempts=0,
            )
            st.rerun()
        attempts = int(st.session_state.get("login_attempts", 0)) + 1
        st.session_state["login_attempts"] = attempts
        if attempts >= 5:
            st.session_state["locked_until"] = time.time() + 60
            st.session_state["login_attempts"] = 0
        st.error("Usuario o contrasena incorrectos.")
    st.stop()


def process_editor_files(files: list[tuple[str, bytes]]) -> tuple[list[dict], list[str]]:
    results, errors = [], []
    progress = st.progress(0)
    for index, (name, data) in enumerate(files, 1):
        try:
            results.append(edit_pdf(Path(name).name, data))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
        progress.progress(index / len(files))
    progress.empty()
    return results, errors


def show_editor_results(results: list[dict], errors: list[str], state_prefix: str) -> None:
    if results:
        zip_key = f"{state_prefix}_zip"
        sha_key = f"{state_prefix}_sha"
        if zip_key not in st.session_state:
            archive = create_editor_zip(results)
            st.session_state[zip_key] = archive
            st.session_state[sha_key] = hashlib.sha256(archive).hexdigest()
        archive = st.session_state[zip_key]
        st.success(f"Listo: {len(results)} PDF editados. ZIP validado: {len(archive)/(1024*1024):.1f} MB")
        st.caption(f"SHA256 del ZIP: {st.session_state[sha_key]}")
        st.download_button(
            "Descargar ZIP con todos los PDF editados",
            data=archive,
            file_name="PDF_EDITADOS.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"{state_prefix}_download_all",
            on_click="ignore",
        )
        for index, item in enumerate(results):
            with st.container(border=True):
                st.write(f"**{item['input_name']}**: {item['input_pages']} -> {item['output_pages']} paginas")
                left, right = st.columns(2)
                left.download_button(
                    "Descargar PDF",
                    item["pdf_data"],
                    item["pdf_name"],
                    "application/pdf",
                    key=f"{state_prefix}_pdf_{index}",
                    on_click="ignore",
                )
                right.download_button(
                    "Auditoria",
                    item["audit_data"],
                    item["audit_name"],
                    "application/json",
                    key=f"{state_prefix}_audit_{index}",
                    on_click="ignore",
                )
    if errors:
        st.error("Algunos archivos no se procesaron")
        for error in errors:
            st.code(error)


st.set_page_config(page_title="Separador y Editor PDF Tecnico", page_icon="📄", layout="wide")
require_login()
st.title("Separador y editor de documentacion tecnica PDF")
st.caption("Separacion por matricula y Editor PDF Tecnico v10")

separator_tab, editor_tab = st.tabs(["1. Separar por matricula", "2. Editor PDF tecnico"])

with separator_tab:
    st.subheader("Separar PDF consolidado")
    st.write("Carga el PDF grande para obtener un documento individual por matricula.")
    consolidated = st.file_uploader("PDF consolidado", type=["pdf"], key="separator_uploader")
    if consolidated and st.button("Separar documentos", type="primary", use_container_width=True):
        try:
            with st.spinner("Analizando y separando todas las paginas..."):
                separated = separate_pdf(consolidated.getvalue())
                st.session_state["separated_result"] = separated
                st.session_state["separated_zip"] = create_separator_zip(separated)
                for key in ("separated_editor_results", "separated_editor_errors", "separated_editor_zip", "separated_editor_sha"):
                    st.session_state.pop(key, None)
        except Exception as exc:
            st.error(f"No fue posible separar el PDF: {exc}")

    separated = st.session_state.get("separated_result")
    if separated:
        st.success(f"Separacion terminada: {len(separated.pdfs)} PDF generados.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Matriculas", len(separated.pdfs))
        c2.metric("Paginas asignadas", sum(len(x) for x in separated.pages_by_registration.values()))
        c3.metric("Paginas por revisar", len(separated.unassigned_pages))
        for warning in separated.warnings:
            st.warning(warning)
        st.download_button(
            "Descargar PDF separados en ZIP",
            st.session_state["separated_zip"],
            "documentos_por_matricula.zip",
            "application/zip",
            use_container_width=True,
            on_click="ignore",
        )

        st.markdown("### Edicion posterior a la separacion")
        st.write("Procesa directamente todos los PDF separados con la logica exacta del Editor PDF Tecnico v10.")
        if st.button("Editar todos los documentos separados", type="primary", use_container_width=True):
            files = sorted(separated.pdfs.items())
            results, errors = process_editor_files(files)
            st.session_state["separated_editor_results"] = results
            st.session_state["separated_editor_errors"] = errors
            st.session_state.pop("separated_editor_zip", None)
            st.session_state.pop("separated_editor_sha", None)
        show_editor_results(
            st.session_state.get("separated_editor_results", []),
            st.session_state.get("separated_editor_errors", []),
            "separated_editor",
        )

with editor_tab:
    st.subheader("Editor PDF tecnico v10")
    st.write("Tambien puedes cargar uno o varios PDF directamente, sin ejecutar la separacion.")
    direct_files = st.file_uploader(
        "Selecciona uno o varios PDF",
        type=["pdf"],
        accept_multiple_files=True,
        key="editor_uploader",
    )
    if not direct_files:
        st.info("Carga al menos un PDF para comenzar.")
    elif st.button("Procesar archivos cargados", type="primary", use_container_width=True):
        files = [(Path(item.name).name, item.getvalue()) for item in direct_files]
        results, errors = process_editor_files(files)
        st.session_state["direct_editor_results"] = results
        st.session_state["direct_editor_errors"] = errors
        st.session_state.pop("direct_editor_zip", None)
        st.session_state.pop("direct_editor_sha", None)
    show_editor_results(
        st.session_state.get("direct_editor_results", []),
        st.session_state.get("direct_editor_errors", []),
        "direct_editor",
    )
