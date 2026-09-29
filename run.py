"""Run the evidence system on Windows, Linux, or macOS using only Python services."""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "services" / "api"))
os.chdir(ROOT)
os.environ.setdefault("DATABASE_URL", "sqlite:///./storage/evidence/local.db")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_PATH", str(ROOT / "storage" / "evidence"))
os.environ.setdefault("QUEUE_MODE", "inline")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local evidence system")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--seed", action="store_true", help="Load synthetic development data and exit"
    )
    args = parser.parse_args()
    secret_path = ROOT / "storage" / "evidence" / "native-secrets.json"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if not secret_path.exists():
        secret_path.write_text(
            json.dumps(
                {
                    "APP_SECRET": secrets.token_urlsafe(48),
                    "ADMIN_PASSWORD": secrets.token_urlsafe(18),
                }
            ),
            encoding="utf-8",
        )
        try:
            secret_path.chmod(0o600)
        except OSError:
            pass
        created = True
    else:
        created = False
    user_supplied_password = "ADMIN_PASSWORD" in os.environ
    local_secrets = json.loads(secret_path.read_text(encoding="utf-8"))
    for key, value in local_secrets.items():
        os.environ.setdefault(key, value)
    if created and not user_supplied_password:
        print(f"Local admin password: {local_secrets['ADMIN_PASSWORD']}")
    from app import models  # noqa: F401
    from app.db import Base, engine

    Base.metadata.create_all(engine)
    if args.seed:
        from app.seed import seed

        print(seed())
        return
    import uvicorn

    print(f"Open http://{args.host}:{args.port} - API docs at /docs")
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
