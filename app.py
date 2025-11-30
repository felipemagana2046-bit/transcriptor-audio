import streamlit as st
import google.generativeai as genai
from docx import Document
import os
import tempfile
import time
from datetime import datetime

# --- FUNCIÓN MÁGICA PARA NEGRITAS ---
def add_markdown_paragraph(doc, text):
    if not text:
        return
    paragraphs = text.split('\n\n')
    for para_text in paragraphs:
        if not para_text.strip():
            continue
        p = doc.add_paragraph()
        parts = para_text.split('**')
        for i, part in enumerate(parts):
            run = p.add_run(part)
            if i % 2 != 0:
                run.bold = True

# 1. Configuración
st.set_page_config(page_title="Transcriptor Pro", page_icon="🎙️", layout="centered")

# 2. Seguridad
api_key = None
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    with st.sidebar:
        api_key = st.text_input("Ingresa tu Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)

# 3. Interfaz
st.title("🎙️ Transcriptor de Audio")

with st.expander("Configuración de Interlocutores", expanded=True):
    main_speaker = st.text_input("Nombre del Interlocutor Principal", value="La Madre")
    other_speakers = st.text_input("Otros interlocutores", placeholder="Ej: Pedro, La Abuela")

# IMPORTANTE: Agregados formatos aac y flac
st.subheader("Archivo de Audio")
uploaded_file = st.file_uploader("Sube tu audio", type=["mp3", "wav", "m4a", "ogg", "aac", "flac"])

if st.button("Transcribir y Generar Word", type="primary"):
    if not api_key or not uploaded_file:
        st.error("⚠️ Faltan datos.")
    else:
        try:
            with st.spinner("Procesando..."):
                # Guardar temporal
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name

                st.text("Subiendo a la nube...")
                myfile = genai.upload_file(tmp_file_path)
                
                # --- LA SOLUCIÓN AL ERROR 500 (SALA DE ESPERA) ---
                # Verifica cada 2 segundos si Google ya terminó de procesar el audio
                processing_placeholder = st.empty()
                while myfile.state.name == "PROCESSING":
                    processing_placeholder.text("⏳ Google está procesando el audio, espera un momento...")
                    time.sleep(2)
                    myfile = genai.get_file(myfile.name)
                
                processing_placeholder.empty() # Limpiar mensaje

                if myfile.state.name == "FAILED":
                    raise ValueError("Google rechazó este archivo de audio (Formato corrupto o no soportado).")

                # Prompt
                speaker_instructions = f"Identifica a la voz principal como **{main_speaker}**."
                if other_speakers:
                    speaker_instructions += f" Distingue también a: {other_speakers}."
                
                system_prompt = f"""
                Actúa como un editor experto. Transcribe LITERALMENTE.
                REGLAS:
                1. {speaker_instructions}
                2. Usa **negritas** (asteriscos dobles) para los nombres.
                3. Párrafos cortos y legibles.
                """

                # --- SELECCIÓN DE MODELO (RESPETANDO TU CONFIGURACIÓN 2.5 y 3) ---
                file_size_mb = uploaded_file.size / (1024 * 1024)
                
                if file_size_mb > 50:
                    model_name = "gemini-2.5-flash"  # MANTENEMOS EL 2.5
                    st.info(f"📂 Archivo grande ({file_size_mb:.1f} MB). Usando Gemini 2.5 Flash.")
                else:
                    model_name = "gemini-3-pro-preview" # MANTENEMOS EL 3 PRO
                    st.success(f"🧠 Archivo ligero. Usando Gemini 3 Pro.")

                st.text(f"Transcribiendo con {model_name}...")
                
                # Generación con Fallback Inteligente
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content([myfile, system_prompt])
                    transcription_text = response.text
                except Exception as e:
                    # Si falla el 3, bajar al 2.5 (nunca al 1.5)
                    if model_name == "gemini-3-pro-preview":
                        st.warning("⚠️ El modelo 3 está saturado. Reintentando con Gemini 2.5 Flash...")
                        model = genai.GenerativeModel("gemini-2.5-flash")
                        response = model.generate_content([myfile, system_prompt])
                        transcription_text = response.text
                    else:
                        raise e

                # Crear Word
                doc = Document()
                doc.add_heading(uploaded_file.name, 0)
                doc.add_paragraph("--- Transcripción ---")
                add_markdown_paragraph(doc, transcription_text)
                
                # Guardar y Descargar
                docx_filename = f"Transcripcion_{uploaded_file.name.rsplit('.', 1)[0]}.docx"
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
                    doc.save(tmp_docx.name)
                    tmp_docx_path = tmp_docx.name
                
                with open(tmp_docx_path, "rb") as f:
                    docx_data = f.read()

                st.success("¡Listo!")
                st.download_button("📥 Descargar Word", data=docx_data, file_name=docx_filename, mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                
                os.unlink(tmp_file_path)
                os.unlink(tmp_docx_path)

        except Exception as e:
            st.error(f"Error: {str(e)}")
