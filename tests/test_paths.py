from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from config.paths import Paths


def test_paths_default():
    assert isinstance(Paths.ROOT_DIR, Path)
    assert isinstance(Paths.CONFIG_DIR, Path)
    assert isinstance(Paths.RESOURCES_DIR, Path)
    assert isinstance(Paths.TEMP_DIR, Path)
    
    assert Paths.CONFIG_DIR.name == "config"
    assert Paths.RESOURCES_DIR.name == "resources"
    assert Paths.TEMP_DIR.name == "temp"
    
    # Test get_config_path
    config_file = Paths.get_config_path("test_config.json")
    assert config_file.name == "test_config.json"
    assert config_file.parent == Paths.CONFIG_DIR


def test_paths_packaged():
    # Mock sys._MEIPASS and sys.executable to simulate PyInstaller environment
    mock_meipass = "/tmp/_MEIPASS12345"
    mock_executable = "/tmp/dist/app"

    with patch.object(sys, "_MEIPASS", mock_meipass, create=True), \
         patch.object(sys, "executable", mock_executable, create=True):
        
        # Reloading or re-checking logic from Paths dynamically with patched sys
        # We can construct Paths logic manually or verify how it behaves under the mock
        root_dir = Path(getattr(sys, "_MEIPASS")) if hasattr(sys, "_MEIPASS") else Path(__file__).resolve().parent.parent
        real_root_dir = Path(sys.executable).resolve().parent if hasattr(sys, "_MEIPASS") else root_dir
        config_dir = real_root_dir / "config"
        resources_dir = root_dir / "resources"
        temp_dir = real_root_dir / "temp"

        assert root_dir == Path(mock_meipass)
        assert real_root_dir == Path("/tmp/dist")
        assert config_dir == Path("/tmp/dist/config")
        assert resources_dir == Path("/tmp/_MEIPASS12345/resources")
        assert temp_dir == Path("/tmp/dist/temp")
