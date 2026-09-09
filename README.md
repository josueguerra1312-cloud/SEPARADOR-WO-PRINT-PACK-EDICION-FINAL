# Separador y Editor PDF Tecnico

Aplicacion integrada en Streamlit para separar un PDF consolidado por matricula y editar posteriormente los documentos con la logica del Editor PDF Tecnico v10.

## Flujo principal

1. Inicio de sesion obligatorio mediante PBKDF2-SHA256.
2. Carga del PDF consolidado.
3. Separacion de todas las paginas por matricula usando campos estructurados `A/C` y `A/C Reg.`.
4. Descarga opcional de los PDF separados.
5. Edicion directa de todos los documentos separados.
6. Generacion de archivos con sufijo ` D.pdf`.
7. Descarga del ZIP validado, auditorias JSON y manifiesto CSV.

La segunda pestana permite cargar uno o varios PDF directamente al editor sin ejecutar previamente la separacion.

## Logica del separador

- Un PDF de salida por matricula.
- Conserva el orden original y copia las paginas PDF originales.
- Relaciona materiales y anexos mediante W/O y Task Card.
- Normaliza variantes como `XAVUK` y `XA-VUK`.
- Ignora matriculas mencionadas libremente dentro de tablas de aplicabilidad o contenido tecnico.
- Crea un reporte de asignacion dentro del ZIP.

## Logica del Editor PDF Tecnico v10

- Elimina hojas `Pre-Draw Print`.
- Detecta Task Cards, Engineering Orders, Daily Checks y Weekly Checks.
- Conserva solamente bloques cuya numeracion este completa.
- Descarta una Task Card de una pagina cuando funciona como portada de una EO o Check consecutivo.
- Agrega una pagina en blanco a cada bloque valido con cantidad impar de paginas.
- Genera auditorias JSON y un manifiesto CSV con SHA-256.
- Usa `ZIP_STORED` y valida CRC, cantidad de archivos y apertura de todos los PDF internos.

## Archivos de la raiz

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

## Ejecucion local

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

macOS o Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

- Main file path: `app.py`
- Python: 3.12
- Todos los archivos deben estar en la raiz del repositorio.

## Seguridad

`users.toml` contiene salts y hashes PBKDF2, no contrasenas en texto plano. En un despliegue futuro se recomienda migrar las credenciales a Streamlit Secrets y rotarlas si el repositorio sera publico.

## Validacion operativa

Antes de producción, revisa el reporte del separador y las auditorias del editor. Si el PDF de entrada es un escaneo sin texto seleccionable, sera necesaria una etapa OCR previa.
