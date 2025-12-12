"""
PURL System Logging Configuration
Perennia AI - Mortgage CRM

Configures structured logging for all PURL components.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_purl_logging(
    log_level: str = None,
    log_dir: str = None,
    console_output: bool = True,
    file_output: bool = True
):
    """
    Configure logging for PURL system components.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        console_output: Enable console logging
        file_output: Enable file logging
    """
    # Get settings from environment
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO")
    log_dir = log_dir or os.getenv("LOG_DIR", "logs")

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - '
        '[%(filename)s:%(lineno)d] - %(message)s'
    )

    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    json_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s", '
        '"file": "%(filename)s", "line": %(lineno)d}'
    )

    # Handlers
    handlers = []

    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))
        console_handler.setFormatter(simple_formatter)
        handlers.append(console_handler)

    if file_output:
        # Main log file
        main_handler = RotatingFileHandler(
            log_path / "purl.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(detailed_formatter)
        handlers.append(main_handler)

        # Error log file
        error_handler = RotatingFileHandler(
            log_path / "purl_error.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        handlers.append(error_handler)

        # JSON log for structured logging
        json_handler = RotatingFileHandler(
            log_path / "purl_json.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=10
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(json_formatter)
        handlers.append(json_handler)

    # Configure PURL loggers
    purl_loggers = [
        "services.purl_workspace_service",
        "services.purl_token_service",
        "services.purl_application_service",
        "services.purl_document_service",
        "services.purl_timeline_service",
        "services.purl_email_service",
        "services.purl_cache_service",
        "middleware.purl_auth",
        "routes.purl_routes",
        "jobs.purl_event_processor",
    ]

    for logger_name in purl_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, log_level))
        logger.handlers = []  # Clear existing handlers
        for handler in handlers:
            logger.addHandler(handler)
        logger.propagate = False

    # Root logger for uncategorized logs
    root_logger = logging.getLogger("purl")
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.handlers = []
    for handler in handlers:
        root_logger.addHandler(handler)

    root_logger.info(f"PURL logging configured: level={log_level}, dir={log_dir}")

    return root_logger


def get_purl_logger(name: str) -> logging.Logger:
    """
    Get a logger for a PURL component.

    Args:
        name: Logger name (e.g., 'workspace_service')

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"purl.{name}")


# Context logging helpers
class PURLLogContext:
    """Context manager for adding context to log messages."""

    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()
        context = self.context

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)


# Usage example:
# with PURLLogContext(logger, workspace_id="abc123", user_id="user456"):
#     logger.info("Processing workspace")


# Audit logging
class PURLAuditLogger:
    """
    Structured audit logger for compliance and security events.
    """

    def __init__(self):
        self.logger = logging.getLogger("purl.audit")

    def log_access(
        self,
        workspace_id: str,
        token_id: str = None,
        user_id: str = None,
        action: str = None,
        resource: str = None,
        ip_address: str = None,
        success: bool = True
    ):
        """Log access attempt."""
        self.logger.info(
            f"ACCESS | workspace={workspace_id} | token={token_id} | "
            f"user={user_id} | action={action} | resource={resource} | "
            f"ip={ip_address} | success={success}"
        )

    def log_token_event(
        self,
        token_id: str,
        event: str,
        workspace_id: str = None,
        user_id: str = None,
        reason: str = None
    ):
        """Log token lifecycle event."""
        self.logger.info(
            f"TOKEN | id={token_id} | event={event} | "
            f"workspace={workspace_id} | user={user_id} | reason={reason}"
        )

    def log_data_event(
        self,
        workspace_id: str,
        event: str,
        entity_type: str,
        entity_id: str = None,
        user_id: str = None,
        changes: dict = None
    ):
        """Log data modification event."""
        self.logger.info(
            f"DATA | workspace={workspace_id} | event={event} | "
            f"type={entity_type} | id={entity_id} | user={user_id} | "
            f"changes={changes}"
        )

    def log_security_event(
        self,
        event: str,
        severity: str,
        workspace_id: str = None,
        token_id: str = None,
        ip_address: str = None,
        details: str = None
    ):
        """Log security-related event."""
        log_method = getattr(self.logger, severity.lower(), self.logger.warning)
        log_method(
            f"SECURITY | event={event} | severity={severity} | "
            f"workspace={workspace_id} | token={token_id} | "
            f"ip={ip_address} | details={details}"
        )


# Singleton instances
audit_logger = PURLAuditLogger()


# Initialize logging when module is imported
if os.getenv("PURL_AUTO_LOGGING", "true").lower() == "true":
    setup_purl_logging()
