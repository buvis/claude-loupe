import logging


def load_settings(path):
    try:
        return open(path).read()
    except OSError as err:
        logging.warning("settings unreadable: %s", err)
        raise
