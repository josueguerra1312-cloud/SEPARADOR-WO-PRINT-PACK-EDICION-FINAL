# Separador y Editor PDF Tecnico v12

Aplicacion Streamlit que separa un PDF consolidado por matricula y permite editar posteriormente cada documento.

## Editor v12

La edicion es conservadora: solo elimina paginas cuando existe una regla positiva y comprobable.

- Elimina `Pre-Draw Print`.
- Elimina Task Cards de una pagina que introducen una EO del mismo identificador.
- Conserva cualquier pagina no clasificada, evitando omisiones silenciosas.
- Conserva anexos que muestran la misma W/O en encabezado, pie o texto extraido.
- Conserva anexos sin numeracion ubicados despues de una tarea y antes del siguiente inicio documental.
- Conserva completa la estructura de `BOROSCOPE INSPECTION`, `BORESCOPE INSPECTION` y `BSI`.
- Reconoce especialmente `VA-72-0102` y `VA-72-0205`.
- Para BSI, agrega la pagina blanca al final del paquete completo, despues de sus anexos.
- Para tareas normales, conserva la paridad validada del bloque principal y mantiene despues sus anexos.
- Infiere una pagina grafica como pagina 1 cuando la siguiente es `PAGE 2 OF N` y coincide la W/O o referencia.
- Genera auditoria JSON, manifiesto CSV, SHA-256 y ZIP validado por CRC.

## Archivos

```text
app.py
pdf_separator.py
pdf_editor_engine.py
users.toml
requirements.txt
runtime.txt
README.md
.gitignore
```

## Ejecucion

```bash
pip install -r requirements.txt
streamlit run app.py
```

En Streamlit Community Cloud: `Main file path: app.py`, Python 3.12.
