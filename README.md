# Burmese Caption Shortener + FFmpeg Burner

This tool is built for short-form **9:16 videos** and Burmese subtitles.
It shortens long SRT captions, auto-adjusts timings, and burns subtitles into the video using ffmpeg.

## File
- `burmese_caption_tool.py`

## Features
- Parse SRT and detect long subtitle lines.
- Split long lines based on `--max-chars`.
- Optional `--min-chars` rebalance.
- Auto timing redistribution for split lines.
- Burn subtitles in **middle-center** position.
- Custom text colors: red, green, yellow, white, black.
- Border/outline styling.
- Optional background box color.
- Custom fonts via `--fonts-dir` and `--font-name`.

## Requirements
- Python 3.9+
- ffmpeg in PATH (`ffmpeg -version` should work)

## Example (Windows paths)
```bash
python burmese_caption_tool.py \
  --input-video "C:\\videos\\clip.mp4" \
  --input-srt "C:\\videos\\clip.srt" \
  --output-video "C:\\videos\\clip_captioned.mp4" \
  --max-chars 16 \
  --min-chars 8 \
  --fonts-dir "C:\\Users\\thaun\\Downloads\\PadaukKyaungChee_Fonts" \
  --font-name "Padauk" \
  --text-color white \
  --outline-color black \
  --bg-color black \
  --outline 2 \
  --use-box \
  --font-size 20 \
  --save-processed-srt "C:\\videos\\clip_processed.srt"
```

## Notes
- If one caption is too long, the tool splits it into multiple subtitle entries and redistributes the original cue duration.
- `--use-box` enables an opaque subtitle background box (uses selected `--bg-color`).
- If you have multiple font folders, run once per folder or copy all `.ttf/.otf` into one folder.

## For your font folders
You can use any one of these as `--fonts-dir`:
- `C:\Users\thaun\Downloads\PadaukKyaungChee_Fonts`
- `C:\Users\thaun\Downloads\koz052_Fonts`
- `C:\Users\thaun\Downloads\MyanmarYinmar_Fonts`
- `C:\Users\thaun\Downloads\MyanmarPhiksel_Fonts`

Use `--font-name` with the exact font family name in that folder.
