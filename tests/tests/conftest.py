import pytest


@pytest.fixture(autouse=True)
def _photo_cache(tmp_path_factory, monkeypatch):
    """Each test gets its own photo cache (in its own temporary folder, not the test's tmp_path), not the one of
    the program run."""
    from quickalignment.ui import photo_cache as pc
    cache = pc.PhotoCache(tmp_path_factory.mktemp("photo_cache_root"))
    monkeypatch.setattr(pc, "_cache", cache)
    yield cache
    cache.clear()
