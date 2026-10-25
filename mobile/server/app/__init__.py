"""ML mini projects API package.

In the slim profile (SERVER_PROFILE=slim) torch and ultralytics must never be imported: they are
not installed on Render and would not fit in 512 MB anyway. A meta-path hook turns any such
import into an ImportError straight away, so a code path that still needs them fails loudly
in local tests instead of silently using hundreds of MB (and libraries that only *optionally*
use torch behave exactly as if it were not installed).
"""
import os
import sys

BLOCKED = ("torch", "torchvision", "ultralytics", "functorch", "torchgen")


class _BlockHeavyImports:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"'{name}' is not available in the slim server profile")
        return None


if os.environ.get("SERVER_PROFILE", "").strip().lower() == "slim" and \
        not any(isinstance(f, _BlockHeavyImports) for f in sys.meta_path):
    sys.meta_path.insert(0, _BlockHeavyImports())
