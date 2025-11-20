"""Centralized browser configuration for stealth mode.

This module provides shared constants for browser automation with anti-detection features.
Used by both BrowserPool and BrowserExecutor to ensure consistency.
"""

from playwright.async_api import ViewportSize

# Chromium launch arguments for stealth mode
# --disable-blink-features=AutomationControlled: Hide automation indicators
# --no-sandbox: Allow running as root (SECURITY TRADEOFF: needed for Docker
#               containers but reduces process isolation. Only use in trusted
#               environments like containerized crawlers, not production web apps)
CHROMIUM_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
]

# Arguments to ignore when launching Chromium
# Removes the --enable-automation flag that signals automated browsing
CHROMIUM_IGNORE_DEFAULT_ARGS = ["--enable-automation"]

# User agent string for stealth mode
# Mimics a standard Chrome browser on Linux
# NOTE: Update periodically to match current Chrome versions
STEALTH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

# Viewport size for stealth mode
# Common desktop resolution to avoid fingerprinting
STEALTH_VIEWPORT: ViewportSize = {"width": 1920, "height": 1080}
