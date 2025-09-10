import base64
import requests
import html
from flask import Flask, request, jsonify, send_file
import io
import os
import re
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from a local .env file in development
load_dotenv()

# Configuration from environment
# ⚠️ WARNING: Never hardcode API keys. Use environment variables.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash-latest:generateContent?key=" + str(GEMINI_API_KEY)
)
AZURE_SPEECH_URL = (
    f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
)

@app.get('/')
def root():
    return send_file('landing.html')

@app.get('/choose')
def choose():
    return send_file('choose.html')

@app.get('/experience')
def experience():
    return send_file('index.html')

# Serve root-level assets (SVGs, fonts) so they load on Heroku
@app.get('/background_mobile.svg')
def asset_bg_mobile():
    return send_file('static/background_mobile.svg')

@app.get('/background_desktop.svg')
def asset_bg_desktop():
    return send_file('static/background_desktop.svg')

@app.get('/GILGONT_.ttf')
def asset_font_gilgon():
    return send_file('static/GILGONT_.ttf')

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@app.route('/narrate', methods=['HEAD'])
def narrate_head():
    return ('', 200)

@app.route('/narrate', methods=['POST'])
def narrate():
    # Validate configuration
    if not GEMINI_API_KEY or not AZURE_SPEECH_KEY:
        return jsonify({"error": "Server missing API configuration. Set GEMINI_API_KEY and AZURE_SPEECH_KEY."}), 500
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"error": "No image data received"}), 400
    history_text = data.get('history', '') or ''
    persona = (data.get('persona') or 'attenborough').lower()

    # 1. Extract and decode the image
    image_data_url = data['image']
    header, encoded_data = image_data_url.split(',', 1)
    
    # 2. Call the AI model API (Gemini)
    # Default to attenborough for now (only available persona)
    persona = 'attenborough'
    persona_style = (
        "You are Sir comedic David Attenborough narrating a Planet Earth style scene with calm, poetic gravitas. "
        "Instead of observing and commenting on animals, you will observe and comment on 'wild humans'. "
        "Comment on the humans' appearance, behavior, and environment as if observing a wild animal. "
        "Refer to the humans as 'wild humans'. "
        "Sprinkle in subtle, clever humor occasionally (no more than once every few lines), poking fun at the humans, "
        "such as a gentle aside about a visible mustache or attire."
    )

    prompt_text = (
        f"{persona_style} Build upon the previous narration without repeating earlier lines. "
        "If nothing substantially new is visible, acknowledge continuity briefly. "
        "Reply with 1–2 concise sentences.\n\n"
        f"Previous narration so far:\n{history_text}\n\n"
        "Now continue with the next line based on the current image."
    )
    
    headers = { "Content-Type": "application/json" }
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": encoded_data}}
            ]
        }]
    }

    try:
        ai_response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        ai_response.raise_for_status() # Raise an error for bad status codes
        narration_text = ai_response.json()['candidates'][0]['content']['parts'][0]['text']
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI API: {e}")
        return jsonify({"error": "Failed to get AI response"}), 500

    # 3. Call the Azure Text-to-Speech API
    # Escape narration text for SSML safety
    safe_text = html.escape(narration_text)
    # Only Attenborough voice available for now
    voice_name = 'en-GB-RyanNeural'
    voice_lang = 'en-GB'
    # Calm, measured prosody for Attenborough
    ssml = f"""
    <speak version='1.0' xml:lang='{voice_lang}'>
        <voice xml:lang='{voice_lang}' xml:gender='Male' name='{voice_name}'>
            <prosody rate='-5%' pitch='-2%'>
                {safe_text}
            </prosody>
        </voice>
    </speak>
    """
    
    tts_headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3", # High quality MP3 format
        "User-Agent": "SirDavidNarratorApp"
    }

    try:
        tts_response = requests.post(AZURE_SPEECH_URL, headers=tts_headers, data=ssml.encode('utf-8'))
        tts_response.raise_for_status()
        audio_b64 = base64.b64encode(tts_response.content).decode('ascii')
        return jsonify({"text": narration_text, "audio": audio_b64})
    except requests.exceptions.RequestException as e:
        print(f"Error calling Azure TTS API: {e}")
        return jsonify({"error": "Failed to generate audio from Azure"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)