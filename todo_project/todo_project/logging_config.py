"""Configuração de logging com envio para syslog."""
import logging
import sys

from todo_project.config import Config


def setup_logging(app) -> None:
    """Configura logger da app com stdout + syslog (RFC5424 ou fallback UDP)."""
    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    app.logger.setLevel(level)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s'
    )

    # Console (desenvolvimento / docker logs)
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        app.logger.addHandler(console)

    if not Config.SYSLOG_ENABLED:
        return

    syslog_handler = _build_syslog_handler(formatter)
    if syslog_handler:
        app.logger.addHandler(syslog_handler)
        app.logger.info('Syslog configurado em %s:%s', Config.SYSLOG_HOST, Config.SYSLOG_PORT)


def _build_syslog_handler(formatter):
    address = (Config.SYSLOG_HOST, Config.SYSLOG_PORT)
    try:
        from rfc5424logging import Rfc5424SysLogHandler
        handler = Rfc5424SysLogHandler(address=address)
    except ImportError:
        import logging.handlers
        handler = logging.handlers.SysLogHandler(address=address, socktype=2)  # UDP
    handler.setFormatter(formatter)
    return handler


class AppLoggerAdapter(logging.LoggerAdapter):
    """Adapter para incluir user, ip e action em cada log."""

    def process(self, msg, kwargs):
        extra = kwargs.setdefault('extra', {})
        extra.setdefault('user', self.extra.get('user', '-'))
        extra.setdefault('ip', self.extra.get('ip', '-'))
        extra.setdefault('action', self.extra.get('action', '-'))
        return msg, kwargs


def get_logger(app, user='-', ip='-', action='-'):
    return AppLoggerAdapter(app.logger, {'user': user, 'ip': ip, 'action': action})
