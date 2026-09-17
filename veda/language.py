"""
V.E.D.A. Multilingual Intelligence Engine: Language Detection & Normalization
Features:
- Automatic language classification: ENGLISH, HINDI, HINGLISH.
- Script analysis (Devanagari vs Latin).
- Lightweight Hinglish normalization (cleans filler noise and colloquialisms).
- Preserves technical names, app titles, paths, numbers, and commands.
"""

import re
from typing import Dict, Any

# Common technical / application terms to preserve strictly
TECHNICAL_TERMS = {
    "chrome", "google chrome", "youtube", "google", "whatsapp", "discord",
    "spotify", "vscode", "vs code", "visual studio code", "v.e.d.a.", "veda",
    "gemini", "windows", "bluetooth", "wi-fi", "wifi", "notepad", "edge",
    "calculator", "calc", "terminal", "powershell", "cmd", "explorer",
    "word", "excel", "powerpoint", "camera", "settings", "volume", "desktop",
    "documents", "downloads", "folder", "file", "battery", "screenshot"
}

# Common Hindi / Hinglish vocabulary words
HINGLISH_INDICATORS = {
    "kholo", "khol", "kholna", "kholiye", "khol do",
    "band", "kar", "karo", "kardo", "karna", "kariye", "kar do",
    "badha", "badhao", "badha do", "badha de", "kam", "ghata",
    "chalao", "chala", "dikhao", "batao", "bata",
    "mera", "meri", "mere", "mujhe", "humko", "apna", "apni",
    "kya", "kyun", "kaise", "kahan", "kab", "kaun",
    "hai", "hain", "hoon", "tha", "the", "thi", "hoga", "hogi",
    "aur", "ya", "lekin", "par", "se", "ko", "mein", "pe", "tak",
    "bhai", "yaar", "thoda", "thodi", "ek", "naya", "nayi", "ye", "yeh", "woh",
    "daal", "daalo", "rakho", "hatao", "delete", "hata", "bhejo"
}

def detect_language(text: str) -> str:
    """
    Classifies utterance into ENGLISH, HINDI, or HINGLISH.
    - HINDI: Contains Devanagari characters or is predominantly Hindi.
    - HINGLISH: Mix of English/Latin script with Hindi words or grammatical markers.
    - ENGLISH: Standard English query.
    """
    if not text or not text.strip():
        return "ENGLISH"

    clean = text.strip()

    # 1. Check for Devanagari characters
    has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in clean)
    if has_devanagari:
        # If it has devanagari mixed with latin technical words, it's conversational Hindi/Hinglish
        words = clean.split()
        latin_words = [w for w in words if any(c.isascii() and c.isalpha() for c in w)]
        if len(latin_words) > 0 and any(w.lower() in TECHNICAL_TERMS for w in latin_words):
            return "HINGLISH"
        return "HINDI"

    # 2. Check for Romanized Hindi / Hinglish words
    tokens = [re.sub(r"[^\w]", "", w).lower() for w in clean.split()]
    tokens = [t for t in tokens if t]

    if not tokens:
        return "ENGLISH"

    hinglish_match_count = sum(1 for t in tokens if t in HINGLISH_INDICATORS)
    tech_match_count = sum(1 for t in tokens if t in TECHNICAL_TERMS)

    # If any strong Hinglish marker exists (e.g. "kholo", "badha do", "mera", "bhai")
    if hinglish_match_count >= 1:
        return "HINGLISH"

    # 3. Check for specific multi-word patterns
    lower_text = clean.lower()
    patterns = [
        r"\b(kar do|kar de|khol do|khol de|band kar|badha do|kam kar)\b",
        r"\b(kya hai|kaise karein|batao|dikhao)\b",
        r"\b(mein daal|ko open karo|pe jao)\b"
    ]
    for p in patterns:
        if re.search(p, lower_text):
            return "HINGLISH"

    return "ENGLISH"

def normalize_hinglish(text: str) -> str:
    """
    Lightweight normalization for Hinglish and Hindi queries:
    - Normalizes common phonetic colloquialisms (e.g., 'badha de' -> 'badha do').
    - Cleans filler words while preserving app names, paths, numbers, and commands.
    """
    if not text:
        return ""

    t = text.strip()

    # Preserve casing for technical words
    substitutions = [
        (r"\b(chrome kholo na|chrome khol na)\b", "Chrome kholo"),
        (r"\b(volume badha de|aawaz badha de)\b", "volume badha do"),
        (r"\b(volume kam kar de|aawaz kam kar de)\b", "volume kam kar do"),
        (r"\b(wifi on kar|wi fi on kar)\b", "Wi-Fi on karo"),
        (r"\b(wifi off kar|wi fi off kar)\b", "Wi-Fi off karo"),
        (r"\b(khol na|kholo na)\b", "kholo"),
        (r"\b(kar na|karo na)\b", "karo"),
        (r"\byoutube\b", "YouTube"),
        (r"\bgoogle\b", "Google"),
        (r"\bchrome\b", "Chrome"),
        (r"\bnotepad\b", "Notepad"),
        (r"\bwhatsapp\b", "WhatsApp"),
        (r"\bdiscord\b", "Discord"),
        (r"\bspotify\b", "Spotify"),
        (r"\bwifi\b", "Wi-Fi"),
        (r"\bwi-fi\b", "Wi-Fi"),
        (r"\bbluetooth\b", "Bluetooth"),
        (r"\bvscode\b", "VS Code"),
        (r"\bvs code\b", "VS Code"),
    ]

    for pat, rep in substitutions:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)

    # Clean double spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t

def prepare_text_for_tts(text: str, language_mode: str) -> str:
    """
    Optimizes text before speech synthesis so neural voice pronounces Roman Hindi phonetically
    instead of pronouncing it with harsh English syllables, while preserving English technical terms.
    """
    if not text:
        return ""
    
    t = text.strip()
    if language_mode in ["HINGLISH", "HINDI"]:
        # Phonetic tweaks for Roman Hindi words that English phoneme models misread
        phonetic_replacements = [
            (r"\bbhai\b", "bhaee"),
            (r"\byaar\b", "yaar"),
            (r"\baaj\b", "aaj"),
            (r"\bkarna\b", "karnaa"),
            (r"\bkholo\b", "kholo"),
            (r"\bkhol\b", "khol"),
            (r"\bkardo\b", "kar do"),
            (r"\bkaafi\b", "kaafi"),
            (r"\btheek\b", "theek"),
            (r"\bhaan\b", "haan"),
            (r"\bhoon\b", "hoon"),
            (r"\bshukriya\b", "shukriyaa"),
            (r"\bnamaste\b", "namaste"),
        ]
        for pat, rep in phonetic_replacements:
            t = re.sub(pat, rep, t, flags=re.IGNORECASE)
            
    return t

def process_voice_transcript(raw_text: str) -> Dict[str, Any]:
    """
    Produces complete language intelligence payload for agent consumption.
    """
    lang_mode = detect_language(raw_text)
    clean = normalize_hinglish(raw_text) if lang_mode in ["HINGLISH", "HINDI"] else raw_text.strip()

    return {
        "raw_transcript": raw_text.strip(),
        "clean_text": clean,
        "language_mode": lang_mode,
        "input_type": "VOICE"
    }
