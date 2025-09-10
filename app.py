import base64
import requests
import html
from flask import Flask, request, jsonify, send_file
import io
import os
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

    # 1. Extract and decode the image
    image_data_url = data['image']
    header, encoded_data = image_data_url.split(',', 1)
    
    # 2. Call the AI model API (Gemini)
    prompt_text = (
        "You are narrating a continuous wildlife documentary in the style of Sir David Attenborough. "
        "Build upon the previous narration without repeating earlier lines. "
        "If nothing substantially new is visible, say something brief acknowledging continuity. "
        "Reply with 1-2 concise sentences.\n\n"
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
    ssml = f"""
    <speak version='1.0' xml:lang='en-US'>
        <voice xml:lang='en-GB' xml:gender='Male' name='en-GB-RyanNeural'>
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