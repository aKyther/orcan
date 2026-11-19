"""Select the Redis package's Supervisor programs using executor settings."""

import sys
from pathlib import Path

# Checkout smoke tests use the same package as the built image.
source = Path(__file__).resolve().parent / "src"
if source.is_dir():
    sys.path.insert(0, str(source))


def programs():
    from orcan_executor.settings import split_lanes, worker_count

    count = worker_count()
    result = [
        "executor-redis",
        "executor-worker",
        "executor-web",
        "executor-maintenance",
        "executor-notifications",
    ]
    result.extend(f"executor-worker-{slot}" for slot in range(2, count + 1))
    if split_lanes():
        result.extend(["executor-worker-light", "executor-worker-heavy"])
    return result


if __name__ == "__main__":
    try:
        print("\n".join(programs()))
    except ValueError as error:
        print(f"Redis plugin: {error}", file=sys.stderr)
        raise SystemExit(1) from None
