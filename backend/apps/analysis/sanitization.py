def sanitize_provider_value(value):
    """Replace PostgreSQL-forbidden null characters in provider-returned values."""
    if isinstance(value, str):
        return value.replace("\x00", "\ufffd")
    if isinstance(value, list):
        return [sanitize_provider_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_provider_value(item) for key, item in value.items()}
    return value
