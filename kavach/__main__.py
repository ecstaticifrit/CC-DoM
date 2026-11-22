import os
from pathlib import Path

import uvicorn

from kavach.app import create_app

db = Path(os.environ.get("KAVACH_DB", "kavach.db"))
uvicorn.run(create_app(db), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
