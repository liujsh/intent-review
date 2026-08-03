from pathlib import Path


def write_atomic(path, text):
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
