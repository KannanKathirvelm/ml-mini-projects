"""Load each project's code in isolation, despite clashing bare module names.

Projects import their own modules by bare name (`import predict`, `from data
import ...`, `import config`), and several projects reuse the same names. For
each project we:

1. stash any sys.modules entries that share a name with one of the project's
   top-level modules/packages (so a previous project's `predict` can't leak in),
2. put the project folder first on sys.path and import the requested modules
   (their own bare imports resolve inside that folder),
3. record every module whose file lives in the project folder, then remove those
   entries from sys.modules and the folder from sys.path, and restore the stash.

The imported module objects keep working afterwards: functions resolve names
through their own module globals, not through sys.modules. None of the 7
projects imports one of its own modules lazily inside a function (checked; only
third-party packages like `anthropic`, `torch`, `cv2` are imported lazily),
so nothing needs the bare names after loading. The tests assert this.
"""
from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable

from .settings import PROJECTS_DIR

PROJECT_DIRS = {
    "credit-card": "01_credit_card_fraud_detection",
    "upi": "02_upi_fraud_detection",
    "stocks": "03_stock_price_prediction_lstm_rnn",
    "finance": "04_financial_ai_agents",
    "prices": "05_price_comparison_app",
    "faces": "06_face_detection",
    "objects": "07_object_detection",
}

_lock = threading.RLock()
_loaded: dict[str, SimpleNamespace] = {}


def project_dir(key: str) -> Path:
    return PROJECTS_DIR / PROJECT_DIRS[key]


def _local_names(root: Path) -> set[str]:
    names = {p.stem for p in root.glob("*.py")}
    names |= {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    names.discard(__name__.split(".")[0])  # never shadow this server's own package
    return names


def _belongs(mod: ModuleType, root: Path) -> bool:
    f = getattr(mod, "__file__", None)
    try:
        return bool(f) and Path(f).resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


def load_modules(root: Path, modules: list[str],
                 before: Callable[[dict[str, ModuleType]], None] | None = None) -> SimpleNamespace:
    """Import `modules` from folder `root` in isolation; returns a namespace of modules.

    `before(mods)` runs after the first module is imported and before the rest,
    which lets a caller patch e.g. `config` before modules that read it import.
    """
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project folder not found: {root} (run ./prepare.sh)")
    with _lock:
        local = _local_names(root)
        stash = {k: sys.modules.pop(k) for k in list(sys.modules)
                 if k.split(".")[0] in local}
        sys.path.insert(0, str(root))
        importlib.invalidate_caches()
        mods: dict[str, ModuleType] = {}
        try:
            for i, name in enumerate(modules):
                mods[name] = importlib.import_module(name)
                if i == 0 and before:
                    before(mods)
        finally:
            for k in [k for k, m in sys.modules.items()
                      if k.split(".")[0] in local and m is not None and _belongs(m, root)]:
                mods.setdefault(k, sys.modules[k])
                del sys.modules[k]
            # also drop any failed/partial entries with local names
            for k in [k for k in sys.modules if k.split(".")[0] in local]:
                del sys.modules[k]
            sys.modules.update(stash)
            try:
                sys.path.remove(str(root))
            except ValueError:
                pass
        ns = SimpleNamespace(**{k.replace(".", "_"): v for k, v in mods.items()})
        ns.__root__ = root
        return ns


def get(key: str, modules: list[str], before=None) -> SimpleNamespace:
    """Cached per-project loader."""
    with _lock:
        if key not in _loaded:
            _loaded[key] = load_modules(project_dir(key), modules, before)
        return _loaded[key]
