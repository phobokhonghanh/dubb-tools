# Project Context

Tài liệu này ghi lại các phần đã triển khai và các quyết định kỹ thuật quan trọng cho v1 Download, v2 Video Splitter, v3 Speech To Text, v4 Translate, v5 Text To Speech, và v6 Merge Video & Audio.

## Kiến trúc hiện tại

- App desktop dùng `Flet`, entrypoint là `main.py`.
- Shell SPA nằm ở `app/shell.py`, dùng sidebar để chuyển giữa các feature.
- Mỗi feature kế thừa `app/features/base.py`.
- Logic nặng đặt trong `utils/`.
- Service background/single-job đặt trong `app/services/`.
- UI feature đặt trong `app/features/`.

Feature hiện có:

- `DownloadView`: `app/features/download_view.py`
- `VideoSplitterView`: `app/features/video_splitter_view.py`
- `SttView`: `app/features/stt_view.py`
- `TranslateView`: `app/features/translate_view.py`
- `TtsView`: `app/features/tts_view.py`
- `MergerView`: `app/features/merger_view.py`

## V1 Download

Các file chính:

- `utils/download.py`: core download logic, streaming/chunking, proxy env, callback progress.
- `download.py`: wrapper tương thích CLI cũ, re-export từ `utils.download`.
- `app/services/download_service.py`: single-job execution cho download.
- `app/features/download_view.py`: UI tải file.

Các thay đổi đã làm:

- Refactor `download.py` thành core reusable trong `utils/download.py`.
- Thêm `DownloadProgress` và `DownloadResult`.
- Hỗ trợ `on_progress`, `on_success`, `on_error`, `stop_event`.
- Vẫn giữ CLI cũ hoạt động qua `download.py`.
- Cho phép chọn thư mục lưu bằng dialog native OS.
- Ưu tiên `zenity` trên Linux, fallback sang `PySide6 QFileDialog`.
- Không dùng `Flet FilePicker` vì runtime hiện tại báo `Unknown control: FilePicker`.
- Lưu state qua tab: URL, thư mục lưu, progress card, file name, speed, size, ETA, busy state, nút mở thư mục.
- Fix realtime khi chuyển tab bằng `_controls`, `_page`, `_sync_controls()`, `_request_ui_refresh()`.

Lưu ý:

- Download có progress realtime thật vì backend nhận chunk từ `requests.iter_content()`.
- `page.call_from_thread()` không tồn tại trong Flet hiện tại, nên dùng `page.schedule_update()`.
- `ft.app()` deprecated, `main.py` đã đổi sang `ft.run(main)`.

## V2 Video Splitter

Các file chính:

- `utils/video_splitter.py`: core logic tách video/audio.
- `app/services/video_splitter_service.py`: single-job execution cho video splitter.
- `app/features/video_splitter_view.py`: UI feature v2.
- `docs/v2_video_to_audio.md`: spec v2 đã cập nhật theo kiến trúc hiện tại.

Output theo spec:

- `<ten_file_goc>_muted.mp4`
- `<ten_file_goc>_vocals.wav`
- `<ten_file_goc>_background.wav`

Các thay đổi đã làm:

- Tạo core `split_video_audio(...)` với `VideoSplitProgress` và `VideoSplitResult`.
- Validate input video: tồn tại, là file, extension thuộc `.mp4`, `.mkv`, `.avi`, `.mov`.
- Dùng `moviepy` để trích xuất audio WAV và export muted video.
- Dùng `sherpa-onnx` source separation với model spleeter ONNX để tách vocals/background.
- Service dùng `Lock`, `Event`, `is_processing` giống download service.
- UI chọn input video và output folder bằng dialog native OS.
- Ưu tiên `zenity`, fallback `PySide6 QFileDialog`.
- UI hiển thị progress dạng stage/indeterminate vì `moviepy` và `sherpa_onnx.process()` không trả % realtime thật.
- Lưu cache qua tab: input video, output folder, progress card, stage text, progress value, busy state, nút mở thư mục.
- Fix callback hoàn tất bị kẹt ở stage cũ bằng cách worker nhận `result` từ service rồi gọi `ui_success`/`ui_error` trực tiếp.
- Fix realtime khi chuyển tab bằng `_controls`, `_page`, `_sync_controls()`, `_request_ui_refresh()`.

Lưu ý:

- Video splitter hiện realtime theo stage, chưa realtime % thật.
- Nếu muốn % thật cho extract/export, cần chuyển một phần sang `ffmpeg` subprocess và parse progress log.
- `sherpa_onnx.OfflineSourceSeparation.process()` là blocking call, khó lấy % thật trong lúc tách.

## V3 Speech To Text

Các file chính:

- `utils/stt_processor.py`: core STT logic.
- `app/services/stt_service.py`: single-job execution cho STT.
- `app/features/stt_view.py`: UI feature v3.
- `extract_text.py`: wrapper tương thích pipeline/CLI cũ, dùng core mới.
- `docs/v3_speech_to_text.md`: spec v3.

Các thay đổi đã làm:

- Tạo core `transcribe_audio(...)` với `SttProgress` và `SttResult`.
- Thêm dataclass `TranscriptSegment` và các hàm:
  - `merge_segments(...)`
  - `normalize_segments(...)`
  - `save_transcript(...)`
  - `stt_result_to_legacy_dict(...)`
- Hỗ trợ input audio: `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`.
- Hỗ trợ chọn language trong UI: `auto`, `vi`, `en`, `zh`, `ja`, `ko`, `fr`, `de`, `es`, `th`.
- Nếu language để trống/chọn `auto`, core chuyển thành `None` để Faster Whisper tự nhận diện ngôn ngữ.
- UI có chọn model: `tiny`, `base`, `small`, `medium`, `large-v3` (mặc định `base`).
- UI có chọn số người nói:
  - `1 người nói`: chạy STT bình thường.
  - `2 người nói` / `Nhiều người nói`: hiển thị `Chức năng sắp ra mắt`.
- Kết quả hiển thị dạng list theo timestamp và có badge tổng số dòng.
- Advanced tools:
  - Gộp dòng theo số N nhập vào.
  - Chuẩn hóa text (khoảng trắng, dấu câu, viết hoa đầu câu mức nhẹ).
- Hỗ trợ lưu kết quả mặc định ra `.srt` trong thư mục output user chọn.
- Tự gợi ý file `*_vocals.wav` mới nhất trong `resources/layer/process` nếu user chưa chọn input audio.
- Lưu state qua tab giống v1/v2:
  - input/output path, model, language, speaker mode, progress card, danh sách kết quả, trạng thái nút.
- Dùng `_controls`, `_page`, `_sync_controls()`, `_request_ui_refresh()` để giảm lỗi mất state khi chuyển tab.

Lưu ý:

- STT realtime ở mức stage + số segment đã nhận diện; không có % tuyệt đối ổn định trong mọi file.
- `extract_text.py` vẫn giữ API/hành vi cũ cho `pipeline_executor.py`, nhưng backend đã dùng core `utils/stt_processor.py`.

## V4 Translate

Các file chính:

- `utils/translator/`: core dịch subtitle theo Strategy Pattern.
- `app/services/translate_service.py`: service single-job cho Translate.
- `app/features/translate_view.py`: UI feature v4.
- `docs/v4_translate.md`: spec v4.

Các thành phần core đã thêm:

- `utils/translator/base.py`: `BaseTranslator`.
- `utils/translator/gemini.py`: `GeminiTranslator` dùng `google-genai`.
- `utils/translator/models.py`: `SrtSegment`, `TranslateProgress`, `TranslateResult`, constants model/language.
- `utils/translator/srt.py`: parse/serialize SRT, chunk policy, output path builder, replace-all helper.

Các thay đổi đã làm:

- Thay `TranslatePlaceholderView` bằng `TranslateView` trong shell.
- Nhận input trực tiếp từ file `.srt`, không phụ thuộc JSONL flow cũ.
- Parse SRT thành segment có `index`, `start_time`, `end_time`, `text`; giữ nguyên timestamp/index khi xuất.
- Context-aware translation:
  - prompt có context summary (full text, tổng dòng, tổng thời lượng, source file, ngôn ngữ đích).
  - yêu cầu AI trả về JSON array đúng số dòng, không markdown.
- Content Safety:
  - nếu bật checkbox, thêm yêu cầu giảm tránh từ ngữ nhạy cảm trong prompt.
- Chunk policy:
  - `< 20` dòng: dịch toàn bộ file trong 1 request.
  - `>= 20` dòng: chia cụm 10 dòng.
- Live preview:
  - cập nhật danh sách kết quả theo từng cụm đã dịch (`on_chunk_done`).
- Post-editing tools:
  - `Replace All` thao tác trực tiếp trên state kết quả đang hiển thị, không gọi lại AI.
- Xuất file:
  - lưu `.srt` dạng `[Tên_File_Gốc]_[Lang].srt`, ví dụ `video_vi.srt`.
- Quản lý API key/config cục bộ:
  - file `config/translator_config.json`.
  - lưu `provider`, `model`, `target_language`, `content_safety`.
  - lưu API key theo model qua map `api_keys[model]` (vẫn tương thích `gemini_api_key` cũ).
- State cache qua tab:
  - input/output path, model, API key, target language, content safety, progress, danh sách dịch, find/replace, output file.
  - đồng bộ bằng `_sync_controls()` + `page.schedule_update()`.

Lưu ý:

- V4 hiện hỗ trợ provider Gemini trước, nhưng core đã tách strategy để mở rộng model/provider sau.
- Progress realtime theo stage/chunk, không theo token stream từng ký tự.
- Khi API lỗi hoặc key sai/hết hạn, UI hiển thị lỗi trong progress/status thay vì treo app.

## V5 Text To Speech

Các file chính:

- `utils/tts/`: core TTS theo Strategy Pattern.
- `app/services/tts_service.py`: service single-job cho TTS.
- `app/features/tts_view.py`: UI feature v5.
- `docs/v5_text_to_speech.md`: spec v5.

Các thành phần core đã thêm:

- `utils/tts/base.py`: `BaseTTS`.
- `utils/tts/edge_tts_provider.py`: `EdgeTTSProvider`.
- `utils/tts/gemini_tts_provider.py`: `GeminiTTSProvider` (dùng `google-genai`).
- `utils/tts/models.py`: `TtsSegment`, `TtsVoice`, `GeneratedSegment`, `TtsProgress`, `TtsResult`.
- `utils/tts/timing.py`: parse segment từ SRT, ffprobe duration, atempo, adjust speed, apply volume.
- `utils/tts/composer.py`: gộp timeline audio theo timestamp bằng ffmpeg + silence.

Các thay đổi đã làm:

- Thêm feature `TtsView` vào shell sau `TranslateView`.
- Hỗ trợ 2 provider:
  - `Edge-TTS` (mặc định, không cần API key).
  - `Gemini TTS` (cần API key, model mặc định `gemini-3.1-flash-tts-preview`).
- Hỗ trợ chọn language và voice; voice list filter theo provider + language.
- Parse input `.srt` để lấy text + mốc thời gian, tạo audio theo từng segment.
- Logic khớp thời gian:
  - nếu audio segment dài hơn slot subtitle thì tăng tốc bằng ffmpeg `atempo`.
  - nếu audio ngắn hơn slot thì giữ nguyên và chèn silence khi compose timeline.
- Với Gemini TTS:
  - không truyền rate/volume trực tiếp vào API.
  - rate/volume xử lý hậu kỳ bằng ffmpeg sau khi sinh segment.
- Output:
  - file tổng: `<stem>_speech.mp3`.
  - thư mục segment: `<stem>_segments/` (nếu bật `Giữ segment lẻ`).
- UI có card config và chú thích cho slider:
  - `Rate`: tăng/giảm tốc độ đọc, có auto speed-up thêm khi cần khớp mốc.
  - `Volume`: chỉnh âm lượng trước khi gộp file tổng.
- State cache qua tab:
  - input/output path, provider, language, voice, api key, rate, volume, keep segments, progress, danh sách segment đã tạo, output file.
  - đồng bộ bằng `_sync_controls()` + `page.schedule_update()`.
- Config local:
  - file `config/tts_config.json`.
  - lưu provider/language/voice/rate/volume/pitch/keep_segments.
  - lưu API key theo provider trong `api_keys`.
- Thêm dependency mới:
  - `edge-tts` trong `requirements.txt`.

Lưu ý:

- `ffmpeg` và `ffprobe` là yêu cầu runtime bắt buộc cho v5.
- `Pitch` đang giữ ở config để mở rộng, chưa áp dụng mạnh cho mọi provider ở v5.
- Thay đổi slider rate/volume sau khi đã tạo xong audio sẽ không tự áp dụng realtime; cần chạy lại job TTS để render output mới.
- Đã fix warning runtime:
  - `RuntimeWarning: coroutine 'list_voices' was never awaited`
  - nguyên nhân do `edge_tts.list_voices()` là coroutine trong ngữ cảnh có event loop.
  - xử lý bằng helper async-safe runner trong `utils/tts/edge_tts_provider.py`.

## V6 Merge Video & Audio

Các file chính:

- `utils/video_merger.py`: core merge video/audio bằng `ffmpeg` và `ffprobe`.
- `app/services/merger_service.py`: service single-job cho merge.
- `app/features/merger_view.py`: UI feature v6.
- `docs/v6_merge.md`: spec v6.

Các thành phần core đã thêm:

- `MediaInfo`: thông tin probe media gồm duration, resolution, fps, video/audio stream.
- `MergeProgress`: stage/message/percent cho UI.
- `MergeResult`: kết quả merge gồm output file, elapsed time và lỗi nếu có.
- `MergeInputSuggestion`: gợi ý input tự động từ thư mục process.

Các thay đổi đã làm:

- Thêm feature `MergerView` vào shell sau `TtsView`.
- Auto-suggest input từ `resources/layer/process`:
  - main video mới nhất theo pattern `*_muted.mp4`.
  - speech audio mới nhất theo pattern `*_speech.mp3`.
  - background audio mới nhất theo pattern `*_background.wav`.
- UI cho phép chọn:
  - `Main Video` bắt buộc.
  - `Speech Audio` bắt buộc.
  - `Background Audio` optional.
  - `Intro Video` optional.
  - `Outro Video` optional.
  - output folder và output filename.
- Output mặc định:
  - `<main_video_stem>_final.mp4`.
- Audio mix:
  - `Speech Volume` slider từ `0%` đến `200%`, mặc định `100%`.
  - `Background Volume` slider từ `0%` đến `200%`, mặc định `125%`.
  - speech/background được delay theo duration của intro video nếu có.
  - mix bằng ffmpeg filter `adelay`, `volume`, `amix`.
- Video pipeline:
  - intro/main/outro được normalize về cùng resolution/fps/pixel format theo main video.
  - concat video bằng ffmpeg concat demuxer.
  - mux video track với audio mix mới.
  - không dùng `-shortest` khi mux để tránh cắt mất outro nếu audio ngắn hơn timeline video.
- Intermediate files:
  - dùng temp folder `.merge_tmp_<stem>/` trong output folder.
  - xóa temp folder khi render thành công.
  - giữ lại nếu lỗi để dễ debug.
- State cache qua tab:
  - main/speech/background path, intro/outro path, output dir/name, speech/background volume, progress, output file.
  - đồng bộ bằng `_sync_controls()` + `page.schedule_update()`.
- Native dialog:
  - ưu tiên `zenity`.
  - fallback `PySide6 QFileDialog`.
  - cancel trả `None`, không fallback tiếp để tránh treo UI.
- Config local:
  - file `config/merger_config.json`.
  - lưu paths gần nhất, output folder/name, speech/background volume.

Lưu ý:

- V6 chỉ hỗ trợ intro/outro là video, chưa hỗ trợ ảnh.
- `ffmpeg` và `ffprobe` là yêu cầu runtime bắt buộc.
- `pipeline_executor.py` không bị thay đổi ở v6.
- Đã smoke test core bằng video/audio mẫu trong `/tmp`, output MP4 có cả video và audio.
- Đã kiểm tra compile bằng `rtk ./venb/bin/python -m compileall app utils main.py`.

## Model và Vendor

Model v2 đang đọc từ:

- `vendor/pyvideotrans/models/onnx/vocals.fp16.onnx`
- `vendor/pyvideotrans/models/onnx/accompaniment.fp16.onnx`

Vendor hiện được chuẩn hóa là dependency local, không commit vào Git. Khi clone project trên máy mới, chạy:

```bash
rtk ./venb/bin/python scripts/ensure_vendor.py
```

Để chỉ kiểm tra vendor:

```bash
rtk ./venb/bin/python scripts/ensure_vendor.py --check
```

Script sẽ bỏ qua clone nếu `vendor/pyvideotrans` đã tồn tại, và validate các file bắt buộc gồm code `prepare_audio.py` cùng 2 model ONNX.

Không nên xóa `vendor/` hiện tại vì:

- `utils/video_splitter.py` đang dùng model trong `vendor/pyvideotrans/models/onnx`.
- `pipeline_executor.py` đang thêm `vendor/pyvideotrans` vào `sys.path`.
- `pipeline_executor.py` import `videotrans.process.prepare_audio`, nên còn phụ thuộc code trong vendor.

Nếu muốn dọn repo sau này:

- Chuyển model sang `models/onnx/`.
- Sửa `V2_MODELS_DIR` trong `utils/video_splitter.py`.
- Kiểm tra và thay thế dependency `videotrans` trong `pipeline_executor.py` trước khi xóa `vendor`.

## Flet version notes

Các lỗi version đã gặp và cách xử lý:

- `ft.padding.only` không tồn tại: đổi sang `ft.Padding(...)`.
- `ft.Expanded` không tồn tại: dùng `ft.Container(expand=True, content=...)`.
- `page.call_from_thread` không tồn tại: dùng `page.schedule_update()`.
- `FilePicker(on_result=...)` không hỗ trợ: bỏ Flet FilePicker.
- `Unknown control: FilePicker`: dùng native OS dialog thay thế.
- `ft.app(target=main)` deprecated: đổi sang `ft.run(main)`.

## Native dialog

Quy ước hiện tại:

- Ưu tiên `zenity` trên Linux.
- Fallback sang `PySide6 QFileDialog`.
- Khi user bấm Cancel, hàm picker phải trả `None` ngay, không chạy tiếp fallback khác để tránh treo UI.

Nơi đang dùng:

- `app/features/download_view.py`: chọn thư mục lưu download.
- `app/features/video_splitter_view.py`: chọn input video và output folder.
- `app/features/stt_view.py`: chọn input audio và output folder transcript.
- `app/features/translate_view.py`: chọn input SRT và output folder bản dịch.
- `app/features/tts_view.py`: chọn input SRT bản dịch và output folder audio.
- `app/features/merger_view.py`: chọn video/audio input, intro/outro và output folder video final.

## RTK workflow

Repo có rule RTK:

- Ưu tiên chạy command dạng `rtk <command>` để giảm token output.
- Tài liệu workflow nằm ở `docs/rtk_workflow.md`.

Một vài command hay dùng:

- `rtk ./venb/bin/python -m compileall app utils main.py extract_text.py`
- `rtk ./venb/bin/python -m compileall app utils main.py translate.py`
- `rtk ./venb/bin/python -m compileall app utils main.py audio_speed.py create_audio.py`
- `rtk ./venb/bin/python -m compileall app utils main.py`
- `rtk ./venb/bin/python main.py`
- `rtk ./venb/bin/flet run main.py`

## Cách chạy app

Khuyến nghị chạy bằng virtual env:

```bash
./venb/bin/python main.py
```

Hoặc:

```bash
./venb/bin/flet run main.py
```

Không nên chạy bằng `/usr/bin/python3` nếu chưa activate env vì hệ thống không có đủ package như `flet`.
