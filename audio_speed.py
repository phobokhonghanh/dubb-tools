import subprocess

def get_duration(file_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.check_output(cmd)
    return float(result.decode().strip())

def build_atempo_filter(speed):
    if speed <= 0:
        raise ValueError("speed must be greater than 0")

    if 0.5 <= speed <= 2.0:
        return f"atempo={speed}"

    parts = []
    temp_speed = speed
    while temp_speed > 2.0:
        parts.append("atempo=2.0")
        temp_speed /= 2.0
    while temp_speed < 0.5:
        parts.append("atempo=0.5")
        temp_speed /= 0.5
    parts.append(f"atempo={temp_speed}")
    return ",".join(parts)

def adjust_speed(input_path, output_path, target_duration, logger=None):
    current_duration = get_duration(input_path)
    if target_duration <= 0:
        raise ValueError("target_duration must be greater than 0")

    # Tốc độ cần thiết: speed = current / target
    # Ví dụ: nếu gốc 3.3s, muốn 2.5s -> speed = 3.3 / 2.5 = 1.32 (nhanh hơn)
    speed = current_duration / target_duration

    message = (
        f"Thời lượng gốc: {current_duration:.2f}s | "
        f"mục tiêu: {target_duration:.2f}s | tốc độ: {speed:.2f}x"
    )
    if logger:
        logger.info(message)
    else:
        print(message)

    filter_str = build_atempo_filter(speed)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-filter:a", filter_str,
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    
    new_duration = get_duration(output_path)
    if logger:
        logger.info("Thời lượng mới: %.2fs", new_duration)
    else:
        print(f"Thời lượng mới: {new_duration:.2f}s")
    return output_path

if __name__ == "__main__":
    adjust_speed("./test_speed.wav", "./test_speed2.wav", 19)
