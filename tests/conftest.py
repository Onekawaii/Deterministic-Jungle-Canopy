"""
Pytest configuration for canopy tests.
"""
import sys
import os

# Add the canopy directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure pytest-asyncio mode
def pytest_configure(config):
    config.option.asyncio_mode = "auto"
