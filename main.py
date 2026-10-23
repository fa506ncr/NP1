"""Convenience launcher; the same CLI is available through python -m bne."""

from bne.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
