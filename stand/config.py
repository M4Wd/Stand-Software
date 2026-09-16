import os

import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.environ.get("STAND_CONFIG", os.path.join(_REPO_ROOT, "config.yaml"))


def load_config(path=None):
    path = path or DEFAULT_CONFIG_PATH
    with open(path) as f:
        config = yaml.safe_load(f)
    mode_override = os.environ.get("STAND_MODE")
    if mode_override:
        config["mode"] = mode_override
    return config


def save_config(config, path=None):
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
