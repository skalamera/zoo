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
    return send_file('index.html')

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
    if persona == 'irwin':
        persona_style = (
            "You are Steve Irwin with enthusiastic Aussie energy. Start EACH sentence with 'Crikey!' "
            "Keep it friendly, excited, and concise (1–2 sentences)."
        )
    else:
        persona = 'attenborough'
        persona_style = (
            "You are Sir David Attenborough narrating a Planet Earth style scene with calm, poetic tone."
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
        if persona == 'irwin':
            # Enforce 'Crikey!' at the start of each sentence
            sentences = re.split(r"(?<=[.!?])\s+", narration_text.strip())
            sentences = [s for s in sentences if s]
            crikey_sentences = []
            for s in sentences:
                s_stripped = s.lstrip()
                if not s_stripped.lower().startswith('crikey!'):
                    s_stripped = f"Crikey! {s_stripped}"
                crikey_sentences.append(s_stripped)
            narration_text = ' '.join(crikey_sentences)
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI API: {e}")
        return jsonify({"error": "Failed to get AI response"}), 500

    # 3. Call the Azure Text-to-Speech API
    # Escape narration text for SSML safety
    safe_text = html.escape(narration_text)
    voice_name = 'en-GB-RyanNeural' if persona == 'attenborough' else 'en-AU-WilliamNeural'
    voice_lang = 'en-GB' if persona == 'attenborough' else 'en-AU'
    if persona == 'irwin':
        # Add enthusiastic prosody for Steve Irwin
        ssml = f"""
        <speak version='1.0' xml:lang='{voice_lang}'>
            <voice xml:lang='{voice_lang}' xml:gender='Male' name='{voice_name}'>
                <prosody rate='+15%' pitch='+10%' volume='+2.5dB'>
                    {safe_text}
                </prosody>
            </voice>
        </speak>
        """
    else:
        ssml = f"""
        <speak version='1.0' xml:lang='{voice_lang}'>
            <voice xml:lang='{voice_lang}' xml:gender='Male' name='{voice_name}'>
                {safe_text}
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