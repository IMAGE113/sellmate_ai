import secrets

def generate_api_key():
    return f"sk_{secrets.token_urlsafe(24)}"
