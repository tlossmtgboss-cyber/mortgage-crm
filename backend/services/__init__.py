"""
Services Package
Business logic and processing services
"""

from .email_processor import EmailProcessor, get_email_processor

__all__ = ['EmailProcessor', 'get_email_processor']
