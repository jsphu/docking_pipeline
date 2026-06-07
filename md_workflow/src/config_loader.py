import json


def load_config(config_file):
    """Loads simulation parameters from a JSON file."""
    with open(config_file, "r") as f:
        return json.load(f)
