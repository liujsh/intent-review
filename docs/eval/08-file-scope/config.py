DEFAULT_TIMEOUT = 30


def timeout(config):
    return config.get("timeout", DEFAULT_TIMEOUT)
