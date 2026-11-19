"""Photos used while the program runs, kept in a temporary folder so they can be picked again without searching
for the files (plate photos with their registration: the corners clicked need not be clicked again).

The folder is made at the first photo and deleted when the program exits (atexit); folders left by a program that
did not exit normally are deleted at the next start once they are older than STALE_DAYS.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

PREFIX = "quickalignment_photos_"
STALE_DAYS = 2.0
PLATE, DEVICE = "plate", "device"


@dataclass
class CachedPhoto:
    kind: str  # PLATE or DEVICE
    path: Path  # copy in the cache folder
    source: str  # original file
    plate: str | None = None  # plate key (plate photos)
    corners: list[tuple[float, float]] = field(default_factory=list)  # clicked points (plate photos)
    use_3d: bool = False
    h: np.ndarray | None = None  # plate -> photo homography of the sample-area plane (plate photos)

    @property
    def label(self) -> str:
        name = Path(self.source).name
        return f"{name} (registered)" if self.h is not None else name


class PhotoCache:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(tempfile.gettempdir())
        self.folder: Path | None = None
        self.photos: list[CachedPhoto] = []

    def _folder(self) -> Path:
        if self.folder is None or not self.folder.exists():
            remove_stale(self.root)
            self.folder = Path(tempfile.mkdtemp(prefix=PREFIX, dir=self.root))
        return self.folder

    def find(self, kind: str, source: str) -> CachedPhoto | None:
        source = str(Path(source).resolve())
        return next((p for p in self.photos if p.kind == kind and p.source == source), None)

    def add(self, kind: str, source: str) -> CachedPhoto | None:
        """Keep a copy of the photo file (once per file and kind); returns its entry (None if it cannot be copied:
        the photo is then simply not remembered)."""
        source = str(Path(source).resolve())
        found = self.find(kind, source)
        if found is not None:
            self.photos.remove(found)
            self.photos.insert(0, found)  # newest first
            return found
        try:
            folder = self._folder()
            target = folder / f"{len(self.photos) + 1:03d}_{Path(source).name}"
            shutil.copy2(source, target)
        except OSError:
            return None
        entry = CachedPhoto(kind, target, source)
        self.photos.insert(0, entry)
        return entry

    def remember_registration(self, source: str, plate: str | None, corners, use_3d: bool,
                              h: np.ndarray | None) -> CachedPhoto | None:
        """A plate photo and the points clicked on it (with the registration they give)."""
        entry = self.add(PLATE, source)
        if entry is not None:
            entry.plate, entry.corners, entry.use_3d = plate, [tuple(map(float, c)) for c in corners], bool(use_3d)
            entry.h = None if h is None else np.array(h, float)
        return entry

    def of_kind(self, kind: str, plate: str | None = None, registered: bool = False) -> list[CachedPhoto]:
        return [p for p in self.photos if p.kind == kind and p.path.exists()
                and (plate is None or p.plate in (None, plate) or kind != PLATE)
                and (not registered or p.h is not None)]

    def clear(self) -> None:
        """Delete the folder and forget the photos (at exit)."""
        if self.folder is not None:
            shutil.rmtree(self.folder, ignore_errors=True)
        self.folder, self.photos = None, []


def remove_stale(root: Path, days: float = STALE_DAYS) -> None:
    """Cache folders left by runs that did not exit normally (older than `days`)."""
    limit = time.time() - days * 86400
    try:
        for d in root.glob(PREFIX + "*"):
            try:
                if d.is_dir() and d.stat().st_mtime < limit:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


_cache: PhotoCache | None = None


def photo_cache() -> PhotoCache:
    """The cache of this run (deleted at exit)."""
    global _cache
    if _cache is None:
        _cache = PhotoCache()
        atexit.register(_cache.clear)
    return _cache
