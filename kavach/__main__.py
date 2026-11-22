import os
from pathlib import Path

import uvicorn


def load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=VALUE lines into the environment without printing them."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

from kavach.app import create_app  # noqa: E402  (reads keys from the environment)

db = Path(os.environ.get("KAVACH_DB", "kavach.db"))
uvicorn.run(create_app(db), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
