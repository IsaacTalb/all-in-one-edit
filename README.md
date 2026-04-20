# Burmese Caption Shortener + FFmpeg Burner

This tool is built for short-form **9:16 videos** and Burmese subtitles.
It shortens long SRT captions by syllable count (max 10 syllables per line), auto-adjusts timings, and burns subtitles into the video using ffmpeg.

## Files
- `burmese_caption_tool.py` - CLI tool with syllable-based splitting
- `burmese_caption_tool_gui.py` - GUI version
- `convert_font.py` - Single font converter
- `convert_fonts.py` - Batch WOFF2 to TTF converter

## Features
- Parse SRT and detect long subtitle lines.
- **Split by syllables** (max 10 syllables per line).
- Auto timing redistribution for split lines.
- Burn subtitles in **middle-center** position.
- Custom text colors: red, green, yellow, white, black.
- Border/outline styling.
- Optional background box color (omit `--use-box` for no background).
- Custom fonts via `--fonts-dir` (auto-detects font name from TTF).

## Requirements
- Python 3.9+
- ffmpeg in PATH (`ffmpeg -version` should work)
- fontTools (`pip install fonttools`) for auto font detection

## Example (Windows paths)
```bash
python burmese_caption_tool.py \
  --input-video "C:\\videos\\clip.mp4" \
  --input-srt "C:\\videos\\clip.srt" \
  --output-video "C:\\videos\\clip_captioned.mp4" \
  --max-syllables 10 \
  --fonts-dir "C:\\Users\\thaun\\Downloads\\MMFreeFonts_CC" \
  --font-name "Z08-Strong" \
  --text-color white \
  --outline-color black \
  --outline 1.5 \
  --font-size 14 \
  --save-processed-srt "C:\\videos\\clip_processed.srt"
```

## Notes
- If one caption has more than 10 syllables, the tool splits it into multiple subtitle entries and redistributes the original cue duration.
- Omit `--use-box` for no background color (text will have outline only).
- Font name is **auto-detected** from TTF metadata if not specified.

## Project Structure
```
C:\isc-kfc\all-in-one-edit\
├── burmese_caption_tool.py      # CLI tool
├── burmese_caption_tool_gui.py # GUI version
├── convert_fonts.py            # Batch WOFF2 to TTF converter
├── raw_video_and_SRT\          # Input videos and SRTs (local only)
│   └── exported_list.txt       # Tracks processed files
├── results\                    # Output videos (local only)
└── .gitignore                  # Excludes local folders from git
```

## Git Ignore Notice
The following folders and files are excluded from GitHub:
- `results/` - Output videos and processed SRTs
- `raw_video_and_SRT/` - Source videos and subtitles
- `exported_list*` - Processing tracking files

These are local working directories only.

## For your font folders
You can use any one of these as `--fonts-dir`:
- `C:\Users\thaun\Downloads\PadaukKyaungChee_Fonts`
- `C:\Users\thaun\Downloads\MMFreeFonts_CC` (Z08-Strong, etc.)
- `C:\Users\thaun\Downloads\MyanmarYinmar_Fonts`
- `C:\Users\thaun\Downloads\MyanmarPhiksel_Fonts`

Font name is auto-detected from the TTF file metadata.
