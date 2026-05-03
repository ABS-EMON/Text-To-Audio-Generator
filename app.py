from flask import Flask, render_template, request, jsonify
import edge_tts
import asyncio
import os
import uuid
from langdetect import detect, LangDetectException

app = Flask(__name__)
AUDIO_DIR = "static/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# edge-tts voice map: (language_code, gender, style) -> voice name
# Run `edge-tts --list-voices` to see all available voices
VOICE_MAP = {
    # English
    ("en", "female", "us"):        "en-US-JennyNeural",
    ("en", "male",   "us"):        "en-US-GuyNeural",
    ("en", "female", "uk"):        "en-GB-SoniaNeural",
    ("en", "male",   "uk"):        "en-GB-RyanNeural",
    ("en", "female", "in"):        "en-IN-NeerjaNeural",
    ("en", "male",   "in"):        "en-IN-PrabhatNeural",

    # Bangla (Bangladesh)
    ("bn", "female", "bd"):        "bn-BD-NabanitaNeural",
    ("bn", "male",   "bd"):        "bn-BD-PradeepNeural",

    # Bangla (India/West Bengal)
    ("bn", "female", "in"):        "bn-IN-TanishaaNeural",
    ("bn", "male",   "in"):        "bn-IN-BashkarNeural",

    # Hindi
    ("hi", "female", "in"):        "hi-IN-SwaraNeural",
    ("hi", "male",   "in"):        "hi-IN-MadhurNeural",

    # Arabic
    ("ar", "female", "sa"):        "ar-SA-ZariyahNeural",
    ("ar", "male",   "sa"):        "ar-SA-HamedNeural",

    # French
    ("fr", "female", "fr"):        "fr-FR-DeniseNeural",
    ("fr", "male",   "fr"):        "fr-FR-HenriNeural",

    # German
    ("de", "female", "de"):        "de-DE-KatjaNeural",
    ("de", "male",   "de"):        "de-DE-ConradNeural",

    # Spanish
    ("es", "female", "es"):        "es-ES-ElviraNeural",
    ("es", "male",   "es"):        "es-ES-AlvaroNeural",

    # Chinese
    ("zh", "female", "cn"):        "zh-CN-XiaoxiaoNeural",
    ("zh", "male",   "cn"):        "zh-CN-YunjianNeural",

    # Japanese
    ("ja", "female", "jp"):        "ja-JP-NanamiNeural",
    ("ja", "male",   "jp"):        "ja-JP-KeitaNeural",

    # Korean
    ("ko", "female", "kr"):        "ko-KR-SunHiNeural",
    ("ko", "male",   "kr"):        "ko-KR-InJoonNeural",

    # Portuguese
    ("pt", "female", "br"):        "pt-BR-FranciscaNeural",
    ("pt", "male",   "br"):        "pt-BR-AntonioNeural",

    # Russian
    ("ru", "female", "ru"):        "ru-RU-SvetlanaNeural",
    ("ru", "male",   "ru"):        "ru-RU-DmitryNeural",

    # Turkish
    ("tr", "female", "tr"):        "tr-TR-EmelNeural",
    ("tr", "male",   "tr"):        "tr-TR-AhmetNeural",
}

# Default fallback voices per language
DEFAULT_VOICE = {
    "en": "en-US-JennyNeural",
    "bn": "bn-BD-NabanitaNeural",
    "hi": "hi-IN-SwaraNeural",
    "ar": "ar-SA-ZariyahNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural",
}

# Language display names
LANG_NAMES = {
    "en": "English", "bn": "Bangla", "hi": "Hindi",
    "ar": "Arabic",  "fr": "French", "de": "German",
    "es": "Spanish", "zh": "Chinese","ja": "Japanese",
    "ko": "Korean",  "pt": "Portuguese","ru": "Russian",
    "tr": "Turkish",
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/detect-language", methods=["POST"])
def detect_language():
    """Auto-detect language from text."""
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text or len(text) < 5:
        return jsonify({"lang": None})
    try:
        lang = detect(text)
        # Map zh-cn/zh-tw → zh
        if lang.startswith("zh"):
            lang = "zh"
        if lang not in LANG_NAMES:
            lang = "en"  # fallback
        return jsonify({"lang": lang, "name": LANG_NAMES.get(lang, lang)})
    except LangDetectException:
        return jsonify({"lang": None})


@app.route("/synthesize", methods=["POST"])
def synthesize():
    data       = request.get_json()
    text       = data.get("text", "").strip()
    sel_lang   = data.get("language", "en")
    gender     = data.get("gender", "female").lower()
    style      = data.get("style", "us").lower()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Detect actual language
    try:
        detected = detect(text)
        if detected.startswith("zh"):
            detected = "zh"
    except LangDetectException:
        detected = sel_lang

    # Warn if mismatch (allow close matches like en-gb vs en)
    detected_base = detected[:2]
    sel_base      = sel_lang[:2]
    mismatch = detected_base != sel_base

    if mismatch:
        det_name = LANG_NAMES.get(detected_base, detected_base)
        sel_name = LANG_NAMES.get(sel_base, sel_base)
        return jsonify({
            "warning": True,
            "detected": detected_base,
            "detected_name": det_name,
            "selected_name": sel_name,
            "message": (
                f"⚠️ Your text appears to be in {det_name}, "
                f"but you selected {sel_name}. "
                f"Switch to {det_name} for best results."
            )
        })

    # Pick voice
    voice = VOICE_MAP.get((sel_base, gender, style)) \
         or DEFAULT_VOICE.get(sel_base, "en-US-JennyNeural")

    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)

    # Run async edge-tts
    async def run_tts():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filepath)

    asyncio.run(run_tts())

    return jsonify({
        "audio_url": f"/static/audio/{filename}",
        "filename":  filename,
        "voice":     voice,
        "warning":   False,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)