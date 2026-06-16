from groq import Groq

_client = None

def get_groq_client() -> Groq:
    global _client
    if _client is None:
        import os
        api_key = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
        _client = Groq(api_key=api_key)
    return _client
