#!/usr/bin/env python3
"""
Burmese Caption Tool - GUI Version
A simple GUI for burning Burmese subtitles into 9:16 videos.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import subprocess
import re
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List


SRT_PATTERN = re.compile(
    r"\s*(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*--\u003e\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str


def srt_time_to_ms(ts: str) -> int:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(",")
    return (
        int(hh) * 3600 * 1000
        + int(mm) * 60 * 1000
        + int(ss) * 1000
        + int(ms)
    )


def ms_to_srt_time(ms: int) -> str:
    ms = max(0, ms)
    hh = ms // 3_600_000
    ms %= 3_600_000
    mm = ms // 60_000
    ms %= 60_000
    ss = ms // 1_000
    ms %= 1_000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def parse_srt(content: str) -> List[Cue]:
    cues: List[Cue] = []
    for m in SRT_PATTERN.finditer(content):
        idx = int(m.group(1))
        start = srt_time_to_ms(m.group(2))
        end = srt_time_to_ms(m.group(3))
        text = m.group(4).strip().replace("\n", " ")
        cues.append(Cue(idx, start, end, text))
    return cues


def split_text_at_spaces(text: str, max_chars: int) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return [""]

    words = text.split(" ")
    chunks: List[str] = []
    current = ""

    for word in words:
        word = word.strip()
        if not word:
            continue
            
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                part = word[i:i + max_chars]
                chunks.append(part)
            continue
        
        if not current:
            current = word
        elif len(current + " " + word) <= max_chars:
            current = current + " " + word
        else:
            chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


def split_cue_by_words(cue: Cue, max_chars: int) -> List[Cue]:
    words = cue.text.split()
    if not words:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, "")]

    # Keep long words intact to avoid breaking Burmese glyph shaping.
    # If a word is longer than max_chars, don't split that cue.
    long_words = [w for w in words if len(w) > max_chars]
    if long_words:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, cue.text.strip())]

    chunks = split_text_at_spaces(cue.text, max_chars)

    if len(chunks) == 1:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, chunks[0])]

    total_duration = max(1, cue.end_ms - cue.start_ms)
    total_chars = sum(len(c) for c in chunks)
    
    out: List[Cue] = []
    start = cue.start_ms
    
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            end = cue.end_ms
        else:
            duration = int((len(chunk) / total_chars) * total_duration)
            end = min(start + duration, cue.end_ms - 1)
            if end <= start:
                end = start + 1
        
        out.append(Cue(0, start, end, chunk))
        start = end

    return out


def escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def escape_style_value(value: str) -> str:
    return value.replace("\\", r"\\").replace("'", r"\'").replace(",", r"\,")


def rebuild_cues(cues: List[Cue], max_chars: int) -> List[Cue]:
    merged: List[Cue] = []
    for cue in cues:
        if len(cue.text) <= max_chars:
            merged.append(Cue(0, cue.start_ms, cue.end_ms, cue.text))
        else:
            merged.extend(split_cue_by_words(cue, max_chars))

    for i, cue in enumerate(merged, start=1):
        cue.index = i
    return merged


def write_srt(cues: List[Cue], path: Path) -> None:
    lines: List[str] = []
    for cue in cues:
        lines.append(str(cue.index))
        lines.append(f"{ms_to_srt_time(cue.start_ms)} --\u003e {ms_to_srt_time(cue.end_ms)}")
        lines.append(cue.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def ass_color(color: str, alpha: str = "00") -> str:
    m = {
        "white": "FFFFFF",
        "black": "000000",
        "red": "FF0000",
        "green": "00FF00",
        "yellow": "FFFF00",
    }
    rgb = m.get(color.lower(), "FFFFFF")
    rr, gg, bb = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H{alpha}{bb}{gg}{rr}"


def ffmpeg_build_features() -> tuple[bool, bool, bool]:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, False, False

    text = f"{proc.stdout}\n{proc.stderr}".lower()
    has_libass = "--enable-libass" in text or "libass" in text
    has_harfbuzz = "--enable-libharfbuzz" in text or "harfbuzz" in text
    has_fribidi = "--enable-libfribidi" in text or "fribidi" in text
    return has_libass, has_harfbuzz, has_fribidi


class CaptionToolGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Burmese Caption Tool")
        self.root.geometry("700x750")
        self.root.minsize(650, 700)
        
        # Variables
        self.video_path = tk.StringVar()
        self.srt_path = tk.StringVar()
        self.fonts_dir = tk.StringVar()
        self.font_name = tk.StringVar()
        self.output_path = tk.StringVar()
        self.save_processed_srt = tk.BooleanVar(value=True)
        
        # Style options
        self.text_color = tk.StringVar(value="white")
        self.outline_color = tk.StringVar(value="black")
        self.bg_color = tk.StringVar(value="black")
        self.font_size = tk.IntVar(value=32)
        self.outline_width = tk.DoubleVar(value=2.0)
        self.use_box = tk.BooleanVar(value=True)
        self.max_chars = tk.IntVar(value=16)
        self.margin_v = tk.IntVar(value=50)
        self.crf = tk.IntVar(value=20)
        self.preset = tk.StringVar(value="medium")
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Title
        title = ttk.Label(main_frame, text="Burmese Caption Tool", font=("Arial", 16, "bold"))
        title.grid(row=row, column=0, columnspan=3, pady=(0, 20), sticky=tk.W)
        row += 1
        
        # Video file
        ttk.Label(main_frame, text="Video File:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.video_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_video).grid(row=row, column=2, padx=5)
        row += 1
        
        # SRT file
        ttk.Label(main_frame, text="SRT File:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.srt_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_srt).grid(row=row, column=2, padx=5)
        row += 1
        
        # Fonts directory
        ttk.Label(main_frame, text="Fonts Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.fonts_dir, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_fonts).grid(row=row, column=2, padx=5)
        row += 1
        
        # Font name
        ttk.Label(main_frame, text="Font Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        font_frame = ttk.Frame(main_frame)
        font_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Entry(font_frame, textvariable=self.font_name, width=30).pack(side=tk.LEFT)
        ttk.Button(font_frame, text="Auto-detect", command=self.auto_detect_font).pack(side=tk.LEFT, padx=(5, 0))
        row += 1
        
        # Output file
        ttk.Label(main_frame, text="Output Video:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse...", command=self.browse_output).grid(row=row, column=2, padx=5)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # Settings section
        settings_frame = ttk.LabelFrame(main_frame, text="Caption Settings", padding="10")
        settings_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        settings_frame.columnconfigure(1, weight=1)
        row += 1
        
        sr = 0
        
        # Max chars
        ttk.Label(settings_frame, text="Max Characters:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(settings_frame, from_=5, to=50, textvariable=self.max_chars, width=10).grid(row=sr, column=1, sticky=tk.W, padx=5)
        ttk.Label(settings_frame, text="(Split captions at this length)").grid(row=sr, column=2, sticky=tk.W)
        sr += 1
        
        # Font size
        ttk.Label(settings_frame, text="Font Size:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(settings_frame, from_=10, to=100, textvariable=self.font_size, width=10).grid(row=sr, column=1, sticky=tk.W, padx=5)
        sr += 1
        
        # Vertical margin
        ttk.Label(settings_frame, text="Vertical Margin:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(settings_frame, from_=0, to=200, textvariable=self.margin_v, width=10).grid(row=sr, column=1, sticky=tk.W, padx=5)
        ttk.Label(settings_frame, text="(Distance from center)").grid(row=sr, column=2, sticky=tk.W)
        sr += 1
        
        # Text color
        ttk.Label(settings_frame, text="Text Color:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        text_color_combo = ttk.Combobox(settings_frame, textvariable=self.text_color, values=["white", "black", "red", "green", "yellow"], width=12, state="readonly")
        text_color_combo.grid(row=sr, column=1, sticky=tk.W, padx=5)
        sr += 1
        
        # Outline color
        ttk.Label(settings_frame, text="Outline Color:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        outline_color_combo = ttk.Combobox(settings_frame, textvariable=self.outline_color, values=["black", "white", "red", "green", "yellow"], width=12, state="readonly")
        outline_color_combo.grid(row=sr, column=1, sticky=tk.W, padx=5)
        sr += 1
        
        # Background color
        ttk.Label(settings_frame, text="Background Color:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        bg_color_combo = ttk.Combobox(settings_frame, textvariable=self.bg_color, values=["black", "white", "red", "green", "yellow"], width=12, state="readonly")
        bg_color_combo.grid(row=sr, column=1, sticky=tk.W, padx=5)
        sr += 1
        
        # Outline width
        ttk.Label(settings_frame, text="Outline Width:").grid(row=sr, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(settings_frame, from_=0, to=5, increment=0.5, textvariable=self.outline_width, width=10).grid(row=sr, column=1, sticky=tk.W, padx=5)
        sr += 1
        
        # Use box
        ttk.Checkbutton(settings_frame, text="Use Background Box", variable=self.use_box).grid(row=sr, column=0, columnspan=2, sticky=tk.W, pady=3)
        sr += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # Video settings section
        video_frame = ttk.LabelFrame(main_frame, text="Video Settings", padding="10")
        video_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        vr = 0
        ttk.Label(video_frame, text="Quality (CRF):").grid(row=vr, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(video_frame, from_=0, to=35, textvariable=self.crf, width=10).grid(row=vr, column=1, sticky=tk.W, padx=5)
        ttk.Label(video_frame, text="(Lower = better quality, 18-23 is good)").grid(row=vr, column=2, sticky=tk.W)
        vr += 1
        
        ttk.Label(video_frame, text="Encoding Preset:").grid(row=vr, column=0, sticky=tk.W, pady=3)
        preset_combo = ttk.Combobox(video_frame, textvariable=self.preset, values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"], width=12, state="readonly")
        preset_combo.grid(row=vr, column=1, sticky=tk.W, padx=5)
        ttk.Label(video_frame, text="(Slower = better quality, slower speed)").grid(row=vr, column=2, sticky=tk.W)
        vr += 1
        
        ttk.Checkbutton(video_frame, text="Save Processed SRT", variable=self.save_processed_srt).grid(row=vr, column=0, columnspan=2, sticky=tk.W, pady=3)
        vr += 1
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # Process button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=10)
        
        self.process_btn = ttk.Button(btn_frame, text="Process Video", command=self.process_video, width=30)
        self.process_btn.pack()
        row += 1
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode="indeterminate", length=400)
        self.progress.grid(row=row, column=0, columnspan=3, pady=10, sticky=(tk.W, tk.E))
        row += 1
        
        # Log output
        ttk.Label(main_frame, text="Log:").grid(row=row, column=0, sticky=tk.W, pady=(10, 5))
        row += 1
        
        self.log_text = scrolledtext.ScrolledText(main_frame, height=8, width=70, wrap=tk.WORD)
        self.log_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        row += 1
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, font=("Arial", 10, "italic"))
        self.status_label.grid(row=row, column=0, columnspan=3, pady=(5, 0), sticky=tk.W)
        
        # Configure grid weights
        main_frame.rowconfigure(row-1, weight=1)  # Make log text expand
        
    def log(self, message: str):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        
    def browse_video(self):
        filename = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv"), ("All files", "*.*")]
        )
        if filename:
            self.video_path.set(filename)
            # Auto-set output path
            if not self.output_path.get():
                path = Path(filename)
                self.output_path.set(str(path.parent / f"{path.stem}_captioned{path.suffix}"))
            # Auto-set SRT path
            if not self.srt_path.get():
                path = Path(filename)
                srt_path = path.parent / f"{path.stem}.srt"
                if srt_path.exists():
                    self.srt_path.set(str(srt_path))
                    
    def browse_srt(self):
        filename = filedialog.askopenfilename(
            title="Select SRT File",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )
        if filename:
            self.srt_path.set(filename)
            
    def browse_fonts(self):
        dirname = filedialog.askdirectory(title="Select Fonts Directory")
        if dirname:
            self.fonts_dir.set(dirname)
            self.auto_detect_font()
            
    def browse_output(self):
        filename = filedialog.asksaveasfilename(
            title="Save Output Video",
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        if filename:
            self.output_path.set(filename)
            
    def auto_detect_font(self):
        """Try to auto-detect font name from the fonts directory"""
        fonts_dir = self.fonts_dir.get()
        if not fonts_dir:
            return
            
        try:
            path = Path(fonts_dir)
            # Look for common font files
            for ext in [".ttf", ".otf", ".TTF", ".OTF"]:
                fonts = list(path.rglob(f"*{ext}"))
                if fonts:
                    # Extract font name from filename
                    font_name = fonts[0].stem.replace("_", " ").replace("-", " ")
                    self.font_name.set(font_name)
                    self.log(f"Auto-detected font: {font_name}")
                    return
            self.log("No font files found in directory")
        except Exception as e:
            self.log(f"Could not auto-detect font: {e}")
            
    def process_video(self):
        # Validate inputs
        if not self.video_path.get():
            messagebox.showerror("Error", "Please select a video file")
            return
        if not self.srt_path.get():
            messagebox.showerror("Error", "Please select an SRT file")
            return
        if not self.output_path.get():
            messagebox.showerror("Error", "Please specify an output path")
            return
            
        # Run in separate thread
        thread = threading.Thread(target=self._process_thread)
        thread.daemon = True
        thread.start()
        
    def _process_thread(self):
        self.process_btn.config(state=tk.DISABLED)
        self.progress.start()
        self.status_var.set("Processing...")
        
        try:
            self._do_process()
        except Exception as e:
            self.root.after(0, lambda: self._on_error(str(e)))
            
    def _on_error(self, message: str):
        self.progress.stop()
        self.process_btn.config(state=tk.NORMAL)
        self.status_var.set("Error occurred")
        messagebox.showerror("Error", message)
        self.log(f"ERROR: {message}")
        
    def _on_success(self):
        self.progress.stop()
        self.process_btn.config(state=tk.NORMAL)
        self.status_var.set("Done!")
        messagebox.showinfo("Success", "Video processed successfully!")
        
    def _do_process(self):
        # Get paths
        video_path = Path(self.video_path.get())
        srt_path = Path(self.srt_path.get())
        output_path = Path(self.output_path.get())

        has_libass, has_harfbuzz, has_fribidi = ffmpeg_build_features()
        if has_libass and has_harfbuzz and has_fribidi:
            self.root.after(0, lambda: self.log("FFmpeg shaping check: libass + harfbuzz + fribidi detected ✅"))
        else:
            self.root.after(0, lambda: self.log("Warning: FFmpeg build may not fully support Myanmar shaping"))
            self.root.after(0, lambda: self.log(f"  libass: {'yes' if has_libass else 'no'}"))
            self.root.after(0, lambda: self.log(f"  harfbuzz: {'yes' if has_harfbuzz else 'no'}"))
            self.root.after(0, lambda: self.log(f"  fribidi: {'yes' if has_fribidi else 'no'}"))
            self.root.after(0, lambda: self.log("Broken output like 'န‌ေ' or 'က ြ' usually means missing shaping libs"))
        fonts_dir = Path(self.fonts_dir.get()) if self.fonts_dir.get() else None
        
        # Validate files exist
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        if not srt_path.exists():
            raise FileNotFoundError(f"SRT not found: {srt_path}")
        if fonts_dir and not fonts_dir.exists():
            raise FileNotFoundError(f"Fonts directory not found: {fonts_dir}")
            
        self.root.after(0, lambda: self.log(f"Processing: {video_path.name}"))
        self.root.after(0, lambda: self.log(f"SRT: {srt_path.name}"))
        
        # Parse and process SRT
        raw_srt = srt_path.read_text(encoding="utf-8-sig")
        cues = parse_srt(raw_srt)
        self.root.after(0, lambda: self.log(f"Loaded {len(cues)} original cues"))
        
        max_chars = self.max_chars.get()
        processed = rebuild_cues(cues, max_chars)
        self.root.after(0, lambda: self.log(f"Split into {len(processed)} output cues"))
        
        # Save processed SRT
        if self.save_processed_srt.get():
            processed_srt_path = output_path.parent / f"{output_path.stem}_processed.srt"
            write_srt(processed, processed_srt_path)
            self.root.after(0, lambda: self.log(f"Saved processed SRT: {processed_srt_path}"))
            temp_srt_path = processed_srt_path
        else:
            # Use temp file
            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode='w', encoding='utf-8') as f:
                lines = []
                for cue in processed:
                    lines.append(str(cue.index))
                    lines.append(f"{ms_to_srt_time(cue.start_ms)} --\u003e {ms_to_srt_time(cue.end_ms)}")
                    lines.append(cue.text)
                    lines.append("")
                f.write("\n".join(lines))
                temp_srt_path = Path(f.name)
                
        # Build subtitle filter
        style = [
            "Alignment=10",  # middle center for 9:16
            f"Fontsize={self.font_size.get()}",
            f"PrimaryColour={ass_color(self.text_color.get())}",
            f"OutlineColour={ass_color(self.outline_color.get())}",
            f"BackColour={ass_color(self.bg_color.get(), alpha='40')}",
            f"Outline={self.outline_width.get()}",
            "Shadow=0",
            f"MarginV={self.margin_v.get()}",
            f"BorderStyle={3 if self.use_box.get() else 1}",
        ]
        if self.font_name.get():
            style.append(f"FontName={escape_style_value(self.font_name.get())}")
            
        srt_escaped = escape_filter_path(temp_srt_path)
        parts = [f"subtitles='{srt_escaped}'", "charenc=UTF-8", "wrap_unicode=1"]
        
        if fonts_dir:
            fonts_escaped = escape_filter_path(fonts_dir)
            parts.append(f"fontsdir='{fonts_escaped}'")
            
        parts.append(f"force_style='{','.join(style)}'")
        subtitles_filter = ":".join(parts)
        
        # Run ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vf", subtitles_filter,
            "-c:v", "libx264",
            "-preset", self.preset.get(),
            "-crf", str(self.crf.get()),
            "-c:a", "copy",
            str(output_path)
        ]
        
        self.root.after(0, lambda: self.log(f"Running ffmpeg..."))
        self.root.after(0, lambda: self.log(f"Command: {' '.join(cmd)}"))
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")
            
        # Cleanup temp file if needed
        if not self.save_processed_srt.get() and temp_srt_path.exists():
            os.unlink(temp_srt_path)
            
        self.root.after(0, lambda: self.log(f"Output saved: {output_path}"))
        self.root.after(0, self._on_success)


def main():
    root = tk.Tk()
    app = CaptionToolGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
