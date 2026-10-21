"""NexusAI — AI-Powered Personal Task Automation.

Phase 1 engineering foundation. This package intentionally keeps its
``__init__`` lightweight so that importing ``nexusai`` does not pull in
optional third-party modules (FastAPI, Streamlit, …) at cost of startup time
or in offline environments.
"""

__version__ = "0.1.0"
__title__ = "NexusAI"

__all__ = ["__title__", "__version__"]
