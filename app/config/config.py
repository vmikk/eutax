"""
Config module for loading EUTAX configuration
"""

import os
import yaml

CONFIG_PATH = os.getenv('EUTAX_CONFIG_PATH', os.path.join(os.path.dirname(__file__), 'eutax.yaml'))

def load_config():
    """
    Load EUTAX configuration (app/config/eutax.yaml)
    Returns an empty dict if the file is missing or invalid
    """
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        # Log or print error
        print(f"Error loading EUTAX config: {e}")
        return {}

