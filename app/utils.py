"""Small stateless helpers shared across the app."""

import random
import re
import string

SENSITIVE_PATTERN = re.compile(r'(=password=|=response=)(.+)', re.IGNORECASE)


def mask(word):
    """Redact password/response values before logging a raw API word."""
    return SENSITIVE_PATTERN.sub(r'\1***', word)


def random_string(length=6, chars=string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"):
    """Generate a random voucher-safe string (default alphabet avoids O/I ambiguity)."""
    return ''.join(random.choice(chars) for _ in range(length))
