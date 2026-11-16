"""Make extracted text safe for PostgreSQL without changing chunk identifiers."""


def clean_record(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [clean_record(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_record(item) for key, item in value.items()}
    return value
