# Streamlit Demo Guide

## 1) Run local demo

Install demo dependency:

pip install -r streamlit_requirements.txt

Run app:

streamlit run streamlit_app.py

Open browser at the local URL shown in terminal.

## 2) What this demo does

- Upload an EPUB file.
- Simulate multi-step processing with progress updates.
- Export a demo EPUB3 output file.

## 3) Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Go to Streamlit Community Cloud and create a new app.
3. Set:
   - Main file path: streamlit_app.py
   - Python version: 3.10+ (recommended)
   - Requirements file: streamlit_requirements.txt
4. Deploy.

## 4) Important note

This demo is local processing only and intended for UI/deployment validation.
For real EPUB to EPUB3 conversion and TTS pipeline execution, connect Streamlit UI to a backend API and worker service.
