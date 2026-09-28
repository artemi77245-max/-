"""Windows executable entry point for the assistant and its isolated worker."""

import sys
import logging

from orbit.config import DATA_ROOT, FROZEN


if __name__ == "__main__":
    if FROZEN:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=DATA_ROOT / "orbit.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--worker" in sys.argv or "--demo" in sys.argv:
        if "--worker" in sys.argv:
            sys.argv.remove("--worker")
        from orbit.worker import main
    else:
        from orbit.supervisor import main
    main()
