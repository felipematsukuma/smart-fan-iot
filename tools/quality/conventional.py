"""Validate a commit title without echoing potentially private commit text."""

import re
import sys
from pathlib import Path


def valid(message: str) -> bool:
    title = message.splitlines()[0] if message.splitlines() else ""
    return bool(
        re.fullmatch(
            r"(?:feat|fix|docs|test|chore|ci|build|refactor|perf|style|revert)(?:\([a-zA-Z0-9_/-]+\))?!?: .+",
            title,
        )
    )


if __name__ == "__main__":
    if not valid(Path(sys.argv[1]).read_text(encoding="utf-8")):
        print("Conventional Commit title required: type(scope): summary")
        raise SystemExit(1)
