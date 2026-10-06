from __future__ import annotations
import hashlib,hmac,time,tomllib
from pathlib import Path
import streamlit as st
from pdf_separator import separate_pdf,build_zip
from pdf_editor_engine import edit_pdf,create_zip
USERS=Path(__file__).with_name('users.toml');AUTH='v12-conservative-annex-bsi'
def login():
 if st.session_state.get('authenticated') and st.session_state.get('auth_version')==AUTH:
  with st.sidebar:
   st.write(f"Usuario: **{st.session_state['username']}**")
   if st.button('Cerrar sesion',use_container_width=True):st.session_state.clear();st.rerun()
  return
 st.title('Acceso al separador y editor PDF');locked=int(float(st.session_state.get('locked_until',0))-time.time())
 if locked>0:st.error(f'Acceso bloqueado. Intenta en {locked} segundos.');st.stop()
 with st.form('login'):
  u=st.text_input('Usuario');p=st.text_input('Contrasena',type='password');ok=st.form_submit_button('Ingresar',type='primary',use_container_width=True)
 if ok:
  with USERS.open('rb') as f:users=tomllib.load(f).get('users',{})
  user=users.get(u.strip());valid=False
  if user:
   actual=hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(user['salt']),int(user['iterations'])).hex();valid=hmac.compare_digest(actual,user['password_hash'])
  if valid:st.session_state.update(authenticated=True,auth_version=AUTH,username=u.strip(),attempts=0);st.rerun()
  a=int(st.session_state.get('attempts',0))+1;st.session_state['attempts']=a
  if a>=5:st.session_state.update(locked_until=time.time()+60,attempts=0)
  st.error('Usuario o contrasena incorrectos.')
 st.stop()
def process(files):
 out=[];err=[];bar=st.progress(0)
 for i,(n,d) in enumerate(files,1):
  try:out.append(edit_pdf(n,d))
  except Exception as e:err.append(f'{n}: {e}')
  bar.progress(i/len(files))
 bar.empty();return out,err
def show(items,err,key):
 if items:
  z=create_zip(items);st.success(f'{len(items)} PDF editados y ZIP validado.');st.download_button('Descargar ZIP editado',z,'PDF_EDITADOS.zip','application/zip',use_container_width=True,key=key+'z')
  for i,x in enumerate(items):
   with st.expander(f"{x['pdf_name']} | {x['input_pages']} -> {x['output_pages']} paginas"):
    a,b=st.columns(2);a.download_button('PDF',x['pdf_data'],x['pdf_name'],'application/pdf',key=f'{key}p{i}');b.download_button('Auditoria',x['audit_data'],x['audit_name'],'application/json',key=f'{key}a{i}')
 for e in err:st.error(e)
st.set_page_config(page_title='Separador y Editor PDF Tecnico',page_icon='📄',layout='wide');login();st.title('Separador y Editor PDF Tecnico v12')
t1,t2=st.tabs(['1. Separar por matricula','2. Editor PDF tecnico'])
with t1:
 f=st.file_uploader('PDF consolidado',type=['pdf'],key='sep')
 if f and st.button('Separar documentos',type='primary',use_container_width=True):st.session_state['sep_result']=separate_pdf(f.getvalue())
 r=st.session_state.get('sep_result')
 if r:
  st.success(f'{len(r.pdfs)} PDF separados.');st.download_button('Descargar separados',build_zip(r),'documentos_por_matricula.zip','application/zip',use_container_width=True)
  if st.button('Editar todos los documentos separados',type='primary',use_container_width=True):st.session_state['sep_edit']=process(sorted(r.pdfs.items()))
  if 'sep_edit' in st.session_state:show(*st.session_state['sep_edit'],'se')
with t2:
 fs=st.file_uploader('Uno o varios PDF',type=['pdf'],accept_multiple_files=True,key='edit')
 if fs and st.button('Procesar archivos',type='primary',use_container_width=True):st.session_state['direct_edit']=process([(x.name,x.getvalue()) for x in fs])
 if 'direct_edit' in st.session_state:show(*st.session_state['direct_edit'],'di')
