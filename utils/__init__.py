import logging


def logger(name=None, level=None):
    """
    A logger.
    :param name: module name
    :param level: debugging level
    :return: a logger instance.
    """

    name = name if name else __name__
    level = level if level else logging.INFO

    _logger = logging.getLogger(name)
    _logger.setLevel(level)
    _hdlr = logging.StreamHandler()
    _fmt = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s] %(message)s"
    )
    _hdlr.setFormatter(_fmt)
    _logger.addHandler(_hdlr)

    return _logger
