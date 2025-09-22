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
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
print(f"Looking for .env file at: {env_path}")
print(f".env file exists: {os.path.exists(env_path)}")
load_dotenv(env_path)

# Configuration from environment
# ⚠️ WARNING: Never hardcode API keys. Use environment variables.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")

# Fallback: If .env loading failed, try to read the file directly
if not GEMINI_API_KEY:
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    GEMINI_API_KEY = line.split('=', 1)[1].strip()
                    break
    except Exception as e:
        print(f"Error reading .env file directly: {e}")

# Debug: Print if API keys are loaded (without revealing the actual keys)
print(f"GEMINI_API_KEY loaded: {'Yes' if GEMINI_API_KEY else 'No'}")
print(f"AZURE_SPEECH_KEY loaded: {'Yes' if AZURE_SPEECH_KEY else 'No'}")
print(f"AZURE_SPEECH_REGION: {AZURE_SPEECH_REGION}")

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

@app.get('/picuisine')
def picuisine():
    return send_file('picuisine.html')

@app.route('/analyze_food', methods=['POST'])
def analyze_food():
    # Validate configuration
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set")
        return jsonify({"error": "Server missing GEMINI_API_KEY configuration."}), 500
    
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"error": "No image data received"}), 400

    # Extract and decode the image
    image_data_url = data['image']
    header, encoded_data = image_data_url.split(',', 1)
    
    # AI prompt for food analysis
    food_analysis_prompt = (
        "You are a helpful food expert and cooking assistant. "
        "Analyze this image and identify any food items, ingredients, or cooking materials visible. "
        "If you see the same ingredients as before, provide the EXACT same recipe suggestions to maintain consistency. "
        "Only change suggestions if you detect new ingredients added or existing ingredients removed. "
        "If no food items are visible, return empty suggestions array. "
        "Provide a brief, encouraging commentary about what you see (1-2 sentences), then suggest 2-4 specific dishes or recipes "
        "that could be made with the visible ingredients. "
        "Format your response as JSON with this structure: "
        "{"
        "  \"commentary\": \"Your helpful observation about the food/ingredients\", "
        "  \"suggestions\": ["
        "    {\"title\": \"Recipe Name\", \"description\": \"Brief description of what can be made\"}, "
        "    {\"title\": \"Recipe Name 2\", \"description\": \"Another dish description\"}"
        "  ]"
        "}"
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [
                {"text": food_analysis_prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": encoded_data}}
            ]
        }]
    }

    try:
        print("Sending request to Gemini API...")
        ai_response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        print(f"Gemini API response status: {ai_response.status_code}")
        ai_response.raise_for_status()
        ai_json_response = ai_response.json()
        print(f"Gemini API response: {ai_json_response}")
        ai_text = ai_json_response['candidates'][0]['content']['parts'][0]['text']
        
        # Parse JSON response from AI
        import json
        try:
            # Clean up the response to extract JSON
            json_start = ai_text.find('{')
            json_end = ai_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                ai_json = json.loads(ai_text[json_start:json_end])
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError):
            # Fallback if JSON parsing fails
            ai_json = {
                "commentary": ai_text[:200] + "..." if len(ai_text) > 200 else ai_text,
                "suggestions": [
                    {"title": "Creative Dish", "description": "Try something creative with your ingredients!"}
                ]
            }
        
        return jsonify({
            "commentary": ai_json.get('commentary', ''),
            "suggestions": ai_json.get('suggestions', [])
        })
        
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI API: {e}")
        return jsonify({"error": "Failed to analyze image"}), 500
    except Exception as e:
        print(f"Unexpected error in analyze_food: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

@app.route('/get_recipe', methods=['POST'])
def get_recipe():
    if not GEMINI_API_KEY:
        return jsonify({"error": "Server missing API configuration."}), 500
    
    data = request.json
    if not data or 'suggestion' not in data:
        return jsonify({"error": "No recipe suggestion received"}), 400

    recipe_prompt = (
        f"Create a detailed recipe for '{data['suggestion']}'. "
        f"Description: {data.get('description', '')}. "
        "Provide a complete recipe with ingredients list, step-by-step instructions, "
        "cooking times, and helpful tips. Format as JSON: "
        "{"
        "  \"title\": \"Recipe Name\", "
        "  \"ingredients\": [\"ingredient 1\", \"ingredient 2\"], "
        "  \"instructions\": [\"step 1\", \"step 2\"], "
        "  \"prepTime\": \"15 minutes\", "
        "  \"cookTime\": \"30 minutes\", "
        "  \"tips\": \"Helpful cooking tips\""
        "}"
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": recipe_prompt}]
        }]
    }

    try:
        ai_response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        ai_response.raise_for_status()
        ai_text = ai_response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # Parse JSON response
        import json
        try:
            json_start = ai_text.find('{')
            json_end = ai_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                recipe_json = json.loads(ai_text[json_start:json_end])
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError):
            # Fallback recipe
            recipe_json = {
                "title": data['suggestion'],
                "ingredients": ["Ingredients will vary based on what you have available"],
                "instructions": ["Follow basic cooking principles", "Adjust seasoning to taste"],
                "prepTime": "Varies",
                "cookTime": "Varies",
                "tips": "Use fresh ingredients when possible and taste as you go!"
            }
        
        return jsonify(recipe_json)
        
    except requests.exceptions.RequestException as e:
        print(f"Error calling AI API: {e}")
        return jsonify({"error": "Failed to generate recipe"}), 500

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
    print("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000, debug=True)