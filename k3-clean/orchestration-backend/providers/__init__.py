"""
Providers package — imports all provider modules to trigger register_provider() calls.

Each provider is imported inside a try/except so that a missing API key (KeyError)
or missing library (ImportError) for one provider does not crash the entire backend.
The remaining providers will still register and be usable.

At startup, check /providers/status to see which providers loaded successfully.
"""

import logging

logger = logging.getLogger(__name__)

_load_errors: dict[str, str] = {}


def _try_import(module_name: str) -> None:
    try:
        __import__(f"providers.{module_name}", fromlist=[module_name])
    except KeyError as e:
        msg = f"Missing API key environment variable: {e}"
        logger.warning("Provider '%s' not loaded — %s", module_name, msg)
        _load_errors[module_name] = msg
    except ImportError as e:
        msg = f"Missing dependency: {e}"
        logger.warning("Provider '%s' not loaded — %s", module_name, msg)
        _load_errors[module_name] = msg
    except Exception as e:
        msg = str(e)
        logger.warning("Provider '%s' not loaded — unexpected error: %s", module_name, msg)
        _load_errors[module_name] = msg


_try_import("anthropic")
_try_import("openai")
_try_import("gemini")
_try_import("perplexity")
_try_import("sunbird")


def get_load_errors() -> dict[str, str]:
    """Returns a map of provider_name → error message for any that failed to load."""
    return dict(_load_errors)
