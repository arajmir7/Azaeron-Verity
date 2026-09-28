"""Start a worker with an isolated, clean multiprocess metrics directory."""

import os
from pathlib import Path
import sys
import tempfile


def main():
    directory = Path(tempfile.gettempdir()) / "verity-worker-metrics"
    directory.mkdir(mode=0o700, exist_ok=True)
    for file in directory.glob("*.db"):
        file.unlink()
    # Set before importing Celery/app/prometheus, inherited by all fork children.
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(directory)
    from app.workers.celery_app import celery_app

    celery_app.worker_main(["worker", *sys.argv[1:]])


if __name__ == "__main__":
    main()
