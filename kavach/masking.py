def mask_account(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isalnum())
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


def mask_email(value: str) -> str:
    _, at, domain = value.partition("@")
    return f"•••@{domain}" if at and domain else "•••"
