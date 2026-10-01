"""Static check: the runtime path (src/) performs no I/O of any kind.

training/ is exempt — it is archival and never imported at runtime.
"""

import re
from pathlib import Path

import forecaster

FORBIDDEN_IMPORTS = {
    # network
    "httpx", "requests", "urllib", "urllib3", "cdsapi", "earthaccess",
    "copernicusmarine", "aiohttp", "http", "ftplib", "smtplib",
    # database
    "sqlalchemy", "psycopg", "psycopg2", "redis", "pymongo",
    # visualization / rendering (the backend renders)
    "matplotlib", "PIL", "rasterio",
    # reprojection (the backend converts to LCC)
    "pyproj", "pyresample",
    # scheduling (the backend schedules)
    "apscheduler", "schedule", "celery",
    # the forecaster is a leaf dependency
    "backend", "frontend",
}

# Runtime-path constructs that must never appear in src/.
FORBIDDEN_SNIPPETS = (
    "loss.backward",     # rule 10: no training in the runtime path
    "torch.optim",       # rule 10
    "FileHandler",       # rule: no logging that writes to a file
    "threading.Timer",   # rule 8: no self-scheduling
    "requests.get",      # rule 4
    "urlopen",           # rule 4
)

IMPORT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)


def _src_dir() -> Path:
    package_dir = Path(forecaster.__file__).resolve().parent
    if package_dir.name != "src":  # repo-root shim mode
        package_dir = package_dir / "src"
    return package_dir


def test_src_exists():
    src = _src_dir()
    assert src.is_dir()
    assert (src / "predict.py").is_file()


def test_no_forbidden_imports_in_runtime_path():
    src = _src_dir()
    offenders = {}
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        top_level = {match.split(".")[0] for match in IMPORT_RE.findall(text)}
        bad = sorted(top_level & FORBIDDEN_IMPORTS)
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"forbidden imports in the runtime path: {offenders}"


def test_no_forbidden_constructs_in_runtime_path():
    src = _src_dir()
    offenders = {}
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        bad = [snippet for snippet in FORBIDDEN_SNIPPETS if snippet in text]
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"forbidden constructs in the runtime path: {offenders}"


def test_runtime_path_never_writes_files():
    """np.save / to_csv / json.dump must never appear in src/ (rule 1)."""
    src = _src_dir()
    offenders = {}
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        bad = [
            token
            for token in ("np.save(", "np.savez(", "to_csv(", "json.dump(")
            if token in text
        ]
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"file writes in the runtime path: {offenders}"


def test_training_dir_is_not_imported():
    """src/ must not import the archival training/ directory or repo code."""
    src = _src_dir()
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "training" not in {
            m.split(".")[0] for m in IMPORT_RE.findall(text)
        }, f"{path.name} imports the archival training/ directory"
