"""Runtime environment variable accessors.

Import these values rather than calling os.getenv() directly in provider
or service modules to keep configuration centralized.
"""

import os

# NASA FIRMS API key — required for fire detection data
NASA_FIRMS_KEY: str | None = os.getenv("NASA_FIRMS_KEY")
