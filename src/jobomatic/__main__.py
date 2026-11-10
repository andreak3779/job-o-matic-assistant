"""``python -m jobomatic``: the same as the ``jobo`` command, without the virtualenv on PATH."""

import sys

from jobomatic.interfaces.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
