"""Human-like Instagram bot powered by UIAutomator2"""

__version__ = "3.2.12"
__tested_ig_version__ = "412.0.0.35.87"

from GramAddict.core.bot_flow import start_bot


def run(**kwargs):
    start_bot(**kwargs)
