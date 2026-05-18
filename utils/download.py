import argparse
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests


ENV_PATH = Path(__file__).with_name(".env")
PROXY_HOST_ENV = "PROXY_HOST"
PROXY_PORT_ENV = "PROXY_PORT"
PROXY_USERNAME_ENV = "PROXY_USERNAME"
PROXY_PASSWORD_ENV = "PROXY_PASSWORD"
DEFAULT_DOWNLOAD_DIR = Path("resources/layer/download")
DEFAULT_CHUNK_SIZE = 1024 * 64
DEFAULT_TIMEOUT_SEC = 30
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass
class DownloadProgress:
    filename: str
    downloaded_bytes: int
    total_bytes: int
    percent: Optional[float]
    speed_mbps: float
    eta_sec: Optional[float]


@dataclass
class DownloadResult:
    ok: bool
    file_path: Optional[str]
    total_bytes: int
    downloaded_bytes: int
    elapsed_sec: float
    error_message: Optional[str]
    http_status: Optional[int]


def load_env_file(env_path=ENV_PATH):
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_proxy_config():
    load_env_file()
    return {
        "proxy_host": os.environ.get(PROXY_HOST_ENV),
        "proxy_port": os.environ.get(PROXY_PORT_ENV),
        "proxy_username": os.environ.get(PROXY_USERNAME_ENV),
        "proxy_password": os.environ.get(PROXY_PASSWORD_ENV),
    }


def ensure_download_dir(base_dir: Path = DEFAULT_DOWNLOAD_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^\w\-.]+", "_", value.strip())
    value = value.strip("._")
    return value or "download"


def guess_extension_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix
    if suffix and len(suffix) <= 10:
        return suffix
    return ".mp4"


def build_output_filename(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or "download").split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    if "." in domain:
        domain = domain.rsplit(".", 1)[0]
    safe_domain = sanitize_filename(domain)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_domain}_{timestamp}{guess_extension_from_url(url)}"


def build_proxies(
    proxy_host=None,
    proxy_port=None,
    proxy_username=None,
    proxy_password=None,
    proxy_address=None,
):
    proxy_host = proxy_host or proxy_address
    if not proxy_host or not proxy_port:
        return None

    if proxy_username and proxy_password:
        proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
    else:
        proxy_url = f"http://{proxy_host}:{proxy_port}"

    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def download(
    url,
    output_filename=None,
    proxy_host=None,
    proxy_port=None,
    proxy_username=None,
    proxy_password=None,
    proxy_address=None,
    use_proxy=True,
    on_progress: Optional[Callable[[DownloadProgress], None]] = None,
    on_success: Optional[Callable[[DownloadResult], None]] = None,
    on_error: Optional[Callable[[DownloadResult], None]] = None,
    stop_event: Optional[threading.Event] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
):
    """
    Tải từ URL và lưu vào file cục bộ theo streaming.
    """
    print("--- Đang bắt đầu tải từ URL ---")
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    proxies = None
    if use_proxy:
        env_proxy = get_proxy_config()
        proxies = build_proxies(
            proxy_host=proxy_host or env_proxy["proxy_host"],
            proxy_port=proxy_port or env_proxy["proxy_port"],
            proxy_username=proxy_username or env_proxy["proxy_username"],
            proxy_password=proxy_password or env_proxy["proxy_password"],
            proxy_address=proxy_address,
        )

    resolved_name = output_filename or build_output_filename(url)
    resolved_path = Path(resolved_name).expanduser()
    if resolved_path.is_absolute() or resolved_path.parent != Path("."):
        output_dir = resolved_path.parent
        file_name = sanitize_filename(resolved_path.name)
    else:
        output_dir = ensure_download_dir()
        file_name = sanitize_filename(resolved_path.name)

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / file_name
    temp_path = final_path.with_suffix(final_path.suffix + ".part")

    started_at = time.monotonic()
    downloaded = 0
    total_size = 0
    http_status = None

    try:
        response = requests.get(
            url,
            headers=headers,
            proxies=proxies,
            stream=True,
            timeout=timeout_sec,
        )
        http_status = response.status_code

        if http_status != 200:
            message = f"Lỗi: Không thể tải. Mã lỗi HTTP: {http_status}"
            print(message)
            result = DownloadResult(
                ok=False,
                file_path=None,
                total_bytes=0,
                downloaded_bytes=0,
                elapsed_sec=time.monotonic() - started_at,
                error_message=message,
                http_status=http_status,
            )
            if on_error:
                on_error(result)
            return result

        total_size = int(response.headers.get("content-length", 0))
        with open(temp_path, "wb") as file:
            for data in response.iter_content(chunk_size):
                if not data:
                    continue
                if stop_event and stop_event.is_set():
                    raise RuntimeError("Tác vụ tải đã bị dừng bởi người dùng.")

                file.write(data)
                downloaded += len(data)

                elapsed = max(time.monotonic() - started_at, 0.001)
                speed_mbps = (downloaded / 1024 / 1024) / elapsed
                percent = (downloaded / total_size * 100.0) if total_size > 0 else None
                eta_sec = (
                    (total_size - downloaded) / (downloaded / elapsed)
                    if total_size > 0 and downloaded > 0
                    else None
                )

                if on_progress:
                    on_progress(
                        DownloadProgress(
                            filename=final_path.name,
                            downloaded_bytes=downloaded,
                            total_bytes=total_size,
                            percent=percent,
                            speed_mbps=speed_mbps,
                            eta_sec=eta_sec,
                        )
                    )

                if total_size > 0:
                    done = int(40 * downloaded / total_size)
                    print(
                        f"\r[{'=' * done}{' ' * (40 - done)}] "
                        f"{downloaded/1024/1024:.2f}MB / {total_size/1024/1024:.2f}MB",
                        end="",
                    )

        temp_path.replace(final_path)
        elapsed = time.monotonic() - started_at
        print(f"\n--- Tải thành công! File lưu tại: {final_path} ---")
        result = DownloadResult(
            ok=True,
            file_path=str(final_path),
            total_bytes=total_size,
            downloaded_bytes=downloaded,
            elapsed_sec=elapsed,
            error_message=None,
            http_status=http_status,
        )
        if on_success:
            on_success(result)
        return result
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        message = f"Đã xảy ra lỗi: {exc}"
        print(message)
        result = DownloadResult(
            ok=False,
            file_path=None,
            total_bytes=total_size,
            downloaded_bytes=downloaded,
            elapsed_sec=time.monotonic() - started_at,
            error_message=message,
            http_status=http_status,
        )
        if on_error:
            on_error(result)
        return result

def main():
    parser = argparse.ArgumentParser(description="Tải file từ URL và lưu cục bộ.")
    parser.add_argument("--url", "-u", required=True, help="URL để tải (bắt buộc)")
    parser.add_argument("--output", "-o", help="Tên file đầu ra (tuỳ chọn)")
    parser.add_argument("--no-proxy", action="store_true", help="Không dùng proxy khi tải file")
    args = parser.parse_args()

    output_name = args.output or build_output_filename(args.url)
    result = download(args.url, output_name, use_proxy=not args.no_proxy)
    raise SystemExit(0 if result.ok else 1)
            
if __name__ == "__main__":
    main()
