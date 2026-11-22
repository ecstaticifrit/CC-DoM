import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.toml")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)
