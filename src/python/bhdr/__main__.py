"""Entry point for ``python -m gpa``.

Dispatches to the user-facing CLI (``bhdr.cli.main``).  The engine launcher
remains accessible explicitly via ``python -m bhdr.launcher``.
"""

import sys

from bhdr.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
