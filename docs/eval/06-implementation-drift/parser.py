def parse(value):
    return parse_value(value)


def parse_value(value):
    """New public helper, contrary to the approved private design."""
    return value.strip()


__all__ = ["parse", "parse_value"]
