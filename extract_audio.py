import os
import argparse
from pathlib import Path
from moviepy import VideoFileClip


DEFAULT_RESOURCES_DIR = Path("resources")
RAW_VIDEO_NAME = "raw_video.mp4"
RAW_AUDIO_NAME = "raw_audio.wav"


def extract_audio(video_path, audio_path):
    """
    Trích xuất âm thanh từ video và lưu thành file WAV.
    """
    print(f"--- Đang trích xuất âm thanh từ: {video_path} ---")
    try:
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path, codec='pcm_s16le', logger=None)
        video.close()
        print(f"--- Đã trích xuất âm thanh thành công: {audio_path} ---")
        return True
    except Exception as e:
        print(f"Lỗi khi trích xuất âm thanh: {e}")
        return False


def save_video_without_audio(video_path, output_path):
    """
    Lưu video không có âm thanh thành file MP4.
    """
    print(f"--- Đang lưu video không âm thanh vào: {output_path} ---")
    try:
        video = VideoFileClip(video_path)
        video_without_audio = video.without_audio()
        video_without_audio.write_videofile(output_path, codec="libx264", audio=False, logger=None)
        video_without_audio.close()
        video.close()
        print(f"--- Đã lưu video không âm thanh thành công: {output_path} ---")
        return True
    except Exception as e:
        print(f"Lỗi khi lưu video không âm thanh: {e}")
        return False


def get_resource_paths(video_path, resources_dir=DEFAULT_RESOURCES_DIR):
    video_path = Path(video_path)
    video_name = video_path.stem
    output_dir = Path(resources_dir) / video_name

    return {
        "output_dir": output_dir,
        "video_path": output_dir / RAW_VIDEO_NAME,
        "audio_path": output_dir / RAW_AUDIO_NAME,
    }


def save_video_and_audio(video_path, resources_dir=DEFAULT_RESOURCES_DIR):
    paths = get_resource_paths(video_path, resources_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    ok = save_video_without_audio(video_path, paths["video_path"])
    if not ok:
        return None

    ok = extract_audio(video_path, paths["audio_path"])
    if not ok:
        return None

    return paths


def main():
    parser = argparse.ArgumentParser(description="Lưu video gốc và trích xuất âm thanh WAV vào thư mục resources")
    parser.add_argument('--video', '-v', required=True, help='Đường dẫn đến file video')
    parser.add_argument(
        '--resources-dir',
        '-o',
        default=DEFAULT_RESOURCES_DIR,
        help='Thư mục output gốc (mặc định: resources)',
    )
    args = parser.parse_args()

    video_path = args.video
    if not os.path.exists(video_path):
        print(f"Lỗi: Không tìm thấy file {video_path}")
        return

    paths = save_video_and_audio(video_path, resources_dir=args.resources_dir)
    if paths is None:
        raise SystemExit(1)

    print(f"Video: {paths['video_path']}")
    print(f"Audio: {paths['audio_path']}")


if __name__ == '__main__':
    main()
