# Separador por matricula y Editor PDF Tecnico

Aplicacion integrada en Streamlit con dos procesos independientes:

1. Separacion de un PDF consolidado por matricula.
2. Edicion tecnica de los PDF separados o de archivos cargados directamente.

## Actualizacion del editor

El modulo de edicion usa la version `v11-annex-wo-bsi` proporcionada por el usuario. La logica del separador no fue modificada.

La nueva logica del editor:

- elimina hojas `P/N Pre-Draw Print`;
- reconoce Task Cards, Engineering Orders, Daily Checks y Weekly Checks;
- valida que las secuencias numeradas esten completas;
- relaciona anexos mediante la W/O;
- conserva anexos asociados a inspecciones BSI aunque el formato del pie sea variable;
- reconoce expresamente las referencias BSI `VA-72-0102` y `VA-72-0205`;
- conserva anexos cuando la tarea o el anexo contiene terminos `BOROSCOPE`, `BORESCOPE` o `BSI`;
- elimina una Task Card de una pagina cuando funciona como portada de una EO o Check consecutivo de la misma W/O;
- agrega una pagina blanca cuando el conjunto conservado del bloque, incluidos sus anexos, tiene una cantidad impar de paginas;
- genera PDF con sufijo ` D.pdf`;
- genera auditoria JSON por archivo;
- genera manifiesto CSV con SHA-256;
- crea un ZIP sin compresion y valida CRC, cantidad de PDF y apertura de los documentos internos.

## Archivos del repositorio

Todos se colocan directamente en la raiz:

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
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

```text
Main file path: app.py
Python: 3.12
```

## Seguridad

`users.toml` contiene hashes PBKDF2-SHA256, no contrasenas en texto plano. Si el repositorio es publico, se recomienda migrar las credenciales a Streamlit Secrets y rotar los hashes actuales.
