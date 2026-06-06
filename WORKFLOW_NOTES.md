# all-in-one-edit orchestration layer

This workspace now includes a durable, file-based pipeline structure for the daily content workflow.

## Intended flow
1. Read Google Sheet rows (URL + Status).
2. Pick pending rows only.
3. Download 5 videos with yt-dlp into `raw_video_and_SRT/raw_video/raw_video_folder`.
4. Convert each to MP3 into `raw_video_and_SRT/raw_audio_eng_mp3/audio_eng_mp3_folder`.
5. Run Whisper to create English SRT into `raw_video_and_SRT/raw_srt_eng_whisper`.
6. Convert English SRT into Burmese paragraph/script into `raw_video_and_SRT/raw_script_mm_codex/raw_script_mm_codex_folder`.
7. Generate Burmese audio with Google Cloud TTS and better-timed Burmese SRT into `raw_video_and_SRT/raw_gcloud_audio_and_genai_srt/gcloud_audio_and_genai_srt_folder`.
8. Burn subtitles / create final content videos into `results/`.

## Notes
- This is structure only; no runtime validation was performed.
- Existing caption tools remain the last-stage video renderer.
- The next useful step is to add a single orchestrator script that coordinates the above folders and delegates to the existing stage scripts.
