"""
AI services for EduMatrix.
Uses configured provider endpoints with minimal token consumption.
"""

import requests
import json
import base64
from django.conf import settings


# ============================
# TEXT GENERATION
# ============================

def gemini_generate(prompt, system_instruction="You are a helpful educational assistant for a school/college LMS platform called EduMatrix. Keep responses concise and helpful.", max_tokens=800):
    """
    Generate text using the configured text-generation endpoint.
    """
    if not settings.GOOGLE_AI_API_KEY:
        return {'success': False, 'error': 'AI tools are not configured on this server.'}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GOOGLE_AI_API_KEY}"
    
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract text from response
        candidates = data.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return {'success': True, 'text': parts[0].get('text', '')}
        
        return {'success': False, 'error': 'No response generated'}
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Request timed out. Please try again.'}
    except requests.exceptions.RequestException:
        return {'success': False, 'error': 'AI request failed. Please try again.'}
    except Exception:
        return {'success': False, 'error': 'AI tools are unavailable right now. Please try again.'}


def gemini_chat(messages, system_instruction="You are EduBot, a friendly and knowledgeable AI study assistant. You help students understand concepts, solve problems, and prepare for exams. Keep explanations clear and concise. Use examples when helpful. If asked about non-educational topics, politely redirect to academic topics."):
    """
    Multi-turn study chat.
    messages: list of dicts with 'role' (user/model) and 'text'
    """
    if not settings.GOOGLE_AI_API_KEY:
        return {'success': False, 'error': 'AI tools are not configured on this server.'}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GOOGLE_AI_API_KEY}"
    
    contents = []
    for msg in messages:
        contents.append({
            "role": msg['role'],
            "parts": [{"text": msg['text']}]
        })
    
    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "maxOutputTokens": 600,
            "temperature": 0.7,
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        candidates = data.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return {'success': True, 'text': parts[0].get('text', '')}
        
        return {'success': False, 'error': 'No response generated'}
    except Exception:
        return {'success': False, 'error': 'AI chat is unavailable right now. Please try again.'}


# ============================
# INDIAN LANGUAGE TOOLS
# ============================

SARVAM_LANGUAGES = {
    'hi-IN': 'Hindi',
    'bn-IN': 'Bengali',
    'ta-IN': 'Tamil',
    'te-IN': 'Telugu',
    'kn-IN': 'Kannada',
    'ml-IN': 'Malayalam',
    'mr-IN': 'Marathi',
    'gu-IN': 'Gujarati',
    'pa-IN': 'Punjabi',
    'od-IN': 'Odia',
    'en-IN': 'English',
}

def sarvam_translate(text, source_lang='en-IN', target_lang='hi-IN'):
    """
    Translate text between Indian languages.
    """
    if not settings.SARVAM_API_KEY:
        return {'success': False, 'error': 'Language tools are not configured on this server.'}

    url = "https://api.sarvam.ai/translate"
    
    headers = {
        'api-subscription-key': settings.SARVAM_API_KEY,
        'Content-Type': 'application/json',
    }
    
    payload = {
        "input": text[:500],  # Limit input to save tokens
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "speaker_gender": "Female",
        "mode": "formal",
        "model": "mayura:v1",
        "enable_preprocessing": True,
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return {'success': True, 'translated_text': data.get('translated_text', '')}
    except Exception:
        return {'success': False, 'error': 'Translation is unavailable right now. Please try again.'}


def sarvam_tts(text, language='hi-IN', speaker='meera'):
    """
    Convert text to speech.
    Returns base64-encoded audio.
    """
    if not settings.SARVAM_API_KEY:
        return {'success': False, 'error': 'Voice tools are not configured on this server.'}

    url = "https://api.sarvam.ai/text-to-speech"
    
    headers = {
        'api-subscription-key': settings.SARVAM_API_KEY,
        'Content-Type': 'application/json',
    }
    
    payload = {
        "inputs": [text[:300]],  # Limit to save tokens
        "target_language_code": language,
        "speaker": speaker,
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": "bulbul:v1",
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        audios = data.get('audios', [])
        if audios:
            return {'success': True, 'audio_base64': audios[0]}
        return {'success': False, 'error': 'No audio generated'}
    except Exception:
        return {'success': False, 'error': 'Voice playback is unavailable right now. Please try again.'}
