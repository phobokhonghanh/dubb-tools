def test_environment():
    """Kiểm tra môi trường kiểm thử đã được cấu hình chính xác."""
    import os
    assert os.environ.get("DUBB_TESTING") == "True"

def test_imports():
    """Kiểm tra việc import các module từ thư mục root."""
    try:
        from utils.download import DEFAULT_DOWNLOAD_DIR
        assert DEFAULT_DOWNLOAD_DIR is not None
    except ImportError as e:
        assert False, f"Không thể import module: {e}"
