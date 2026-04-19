importimport secrets

def generate_api_key():
    return "sk_" + secrets.token_urlsafe(32)
