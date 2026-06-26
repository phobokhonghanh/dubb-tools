from __future__ import annotations

import subprocess
import threading
import sys
import atexit
from pathlib import Path
from typing import List, Optional, Union

class ProcessManager:
    _active_processes: List[subprocess.Popen] = []
    _lock = threading.Lock()

    @classmethod
    def register_process(cls, popen_obj: subprocess.Popen) -> None:
        with cls._lock:
            cls._active_processes.append(popen_obj)

    @classmethod
    def unregister_process(cls, popen_obj: subprocess.Popen) -> None:
        with cls._lock:
            if popen_obj in cls._active_processes:
                cls._active_processes.remove(popen_obj)

    @classmethod
    def kill_all(cls) -> None:
        """Dừng và giải phóng tất cả các tiến trình con đang chạy."""
        with cls._lock:
            processes = list(cls._active_processes)
            cls._active_processes.clear()
        
        for p in processes:
            if p.poll() is None:  # Tiến trình vẫn đang chạy
                try:
                    p.terminate()
                except Exception:
                    pass
        
        for p in processes:
            try:
                p.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                    p.wait(timeout=0.1)
                except Exception:
                    pass

# Đăng ký tự động dọn dẹp khi ứng dụng thoát
atexit.register(ProcessManager.kill_all)

def run_process(
    args: List[Union[str, Path]],
    *,
    check: bool = True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """
    Chạy một tiến trình con an toàn, đăng ký vào ProcessManager để quản lý vòng đời.
    """
    str_args = [str(arg) for arg in args]
    
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    popen_obj = subprocess.Popen(
        str_args,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        startupinfo=startupinfo,
    )
    
    ProcessManager.register_process(popen_obj)
    
    try:
        out, err = popen_obj.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        popen_obj.kill()
        out, err = popen_obj.communicate()
        ProcessManager.unregister_process(popen_obj)
        raise subprocess.TimeoutExpired(popen_obj.args, timeout, output=out, stderr=err)
    except Exception:
        popen_obj.kill()
        try:
            popen_obj.wait(timeout=0.2)
        except Exception:
            pass
        ProcessManager.unregister_process(popen_obj)
        raise
    
    ProcessManager.unregister_process(popen_obj)
    
    retcode = popen_obj.poll()
    if check and retcode:
        raise subprocess.CalledProcessError(
            retcode, popen_obj.args, output=out, stderr=err
        )
        
    return subprocess.CompletedProcess(
        popen_obj.args, retcode, out, err
    )
