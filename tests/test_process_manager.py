import subprocess
import time
import pytest
from utils.process import ProcessManager, run_process

def test_run_process_success():
    """Kiểm tra chạy tiến trình con thành công."""
    res = run_process(["echo", "hello"])
    assert res.returncode == 0
    assert b"hello" in res.stdout

def test_run_process_failure():
    """Kiểm tra khi tiến trình con trả về mã lỗi."""
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        run_process(["false"])
    assert excinfo.value.returncode == 1

def test_process_manager_kill_all():
    """Kiểm tra ProcessManager.kill_all dọn dẹp các tiến trình đang chạy."""
    # Khởi chạy một tiến trình sleep dài ngày
    popen_obj = subprocess.Popen(["sleep", "10"])
    ProcessManager.register_process(popen_obj)
    
    # Đảm bảo tiến trình đang chạy
    assert popen_obj.poll() is None
    
    # Hủy toàn bộ tiến trình
    ProcessManager.kill_all()
    
    # Đợi ngắn và kiểm tra tiến trình đã bị kết thúc
    time.sleep(0.1)
    assert popen_obj.poll() is not None
