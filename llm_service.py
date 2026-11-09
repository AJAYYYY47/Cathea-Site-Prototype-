import json
import os
import urllib.request
import urllib.error

def query_llm(user_message, conversation_history, site_settings):
    """
    Cathea Studio AI Consultation Service
    """
    provider = site_settings.llm_provider if site_settings else 'mock'
    api_key = site_settings.llm_api_key if site_settings and site_settings.llm_api_key else os.environ.get('LLM_API_KEY', '')
    system_prompt = site_settings.llm_system_prompt if site_settings else "You are Cathea Studio Assistant."

    user_lower = user_message.lower()
    wants_human = any(k in user_lower for k in [
        'human', 'real person', 'whatsapp', 'wa', 'speak to someone', 'talk to someone', 
        'representative', 'manager', 'director', 'book now', 'urgent', 'call', 'contact'
    ])

    if provider == 'gemini' and api_key:
        try:
            return query_gemini(user_message, conversation_history, system_prompt, api_key, wants_human)
        except Exception as e:
            print(f"[LLM Error] Gemini failed: {e}")

    elif provider == 'openai' and api_key:
        try:
            return query_openai(user_message, conversation_history, system_prompt, api_key, wants_human)
        except Exception as e:
            print(f"[LLM Error] OpenAI failed: {e}")

    return cathea_mock_response(user_message, wants_human)


def cathea_mock_response(message, wants_human):
    msg = message.lower().strip()

    if wants_human:
        return {
            'reply': "I can connect you directly with our studio director on WhatsApp right now to discuss dates and package options. Tap 'Continue on WhatsApp' below to proceed.",
            'suggest_whatsapp': True
        }

    # Portfolio & Instagram
    if any(k in msg for k in ['portfolio', 'work', 'instagram', 'photos', 'gallery', 'style', 'sample']):
        return {
            'reply': "Cathea Studio specializes in wedding, prewedding, and intimate portraiture across Batam, Singapore, and destination locations. Our latest works are featured in our Photos tab and daily on Instagram @cathea.studio. Would you like to review specific packages?",
            'suggest_whatsapp': False
        }

    # Location / Batam / Singapore
    if any(k in msg for k in ['where', 'location', 'batam', 'singapore', 'studio', 'address', 'travel']):
        return {
            'reply': "Cathea Studio is based in Batam and frequently photographs couples across Singapore, Bali, and regional destinations. We are available worldwide for destination bookings.",
            'suggest_whatsapp': False
        }

    # Pricing & Packages
    if any(k in msg for k in ['price', 'pricing', 'rate', 'cost', 'how much', 'package', 'fee']):
        return {
            'reply': "We offer curated collections for Prewedding Sessions, Full Wedding Day Coverage, and Studio Editorial Portraiture. Each package is tailored to your schedule and location requirements. Would you like to speak directly with our director on WhatsApp for an exact quote?",
            'suggest_whatsapp': True
        }

    # Booking & Availability
    if any(k in msg for k in ['book', 'booking', 'date', 'available', 'availability', 'schedule', 'reserve']):
        return {
            'reply': "We recommend reserving wedding and prewedding dates 2 to 6 months in advance. You can consult directly with our studio director on WhatsApp to check your exact calendar date.",
            'suggest_whatsapp': True
        }

    # Greetings
    if any(k in msg for k in ['hi', 'hello', 'hey', 'halo', 'good morning', 'good afternoon']):
        return {
            'reply': "Greetings. Welcome to Cathea Studio (@cathea.studio). I am your consultation assistant. How may I assist your wedding or photography inquiry today?",
            'suggest_whatsapp': False
        }

    return {
        'reply': "Thank you for reaching out to Cathea Studio. We document authentic weddings, preweddings, and cinema reels in Batam, Singapore, and worldwide (@cathea.studio). Feel free to ask questions or tap to consult directly via WhatsApp.",
        'suggest_whatsapp': False
    }


def query_gemini(message, history, system_prompt, api_key, wants_human):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM: {system_prompt}"}]},
        {"role": "model", "parts": [{"text": "Understood. I will act as Cathea Studio assistant."}]}
    ]
    for h in history[-6:]:
        contents.append({
            "role": "user" if h.get("sender") == "user" else "model",
            "parts": [{"text": h.get("text", "")}]
        })
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = json.dumps({"contents": contents}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode('utf-8'))
        reply_text = result['candidates'][0]['content']['parts'][0]['text']
        return {
            'reply': reply_text,
            'suggest_whatsapp': wants_human or 'whatsapp' in reply_text.lower()
        }


def query_openai(message, history, system_prompt, api_key, wants_human):
    url = "https://api.openai.com/v1/chat/completions"
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:
        messages.append({
            "role": "user" if h.get("sender") == "user" else "assistant",
            "content": h.get("text", "")
        })
    messages.append({"role": "user", "content": message})

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": messages,
        "max_tokens": 250,
        "temperature": 0.7
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
    )
    
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode('utf-8'))
        reply_text = result['choices'][0]['message']['content']
        return {
            'reply': reply_text,
            'suggest_whatsapp': wants_human or 'whatsapp' in reply_text.lower()
        }
