"""
Convert all WOFF2 fonts to TTF format using fonttools.
Run this for the three font directories.
"""

from fontTools.ttLib import TTFont
from pathlib import Path
import sys

def convert_woff2_to_ttf(input_path: Path, output_path: Path = None):
    """Convert a WOFF2 font to TTF format."""
    try:
        font = TTFont(str(input_path))
        if output_path is None:
            output_path = input_path.with_suffix('.ttf')
        font.flavor = None  # Remove WOFF2 flavor to make it TTF
        font.save(str(output_path))
        print(f"Converted: {input_path.name} -> {output_path.name}")
        return True
    except Exception as e:
        print(f"Error converting {input_path}: {e}")
        return False

def process_font_directory(directory: Path):
    """Process all WOFF2 files in a directory recursively."""
    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    print(f"\nProcessing: {directory}")
    print("=" * 50)

    woff2_files = list(directory.rglob("*.woff2"))

    if not woff2_files:
        print("No .woff2 files found")
        return

    for woff2_file in woff2_files:
        # Create TTF in same directory
        ttf_path = woff2_file.with_suffix('.ttf')
        convert_woff2_to_ttf(woff2_file, ttf_path)

if __name__ == "__main__":
    # Process all three font directories
    directories = [
        Path(r"C:\Users\thaun\Downloads\MyanmarYinmar_Fonts"),
        Path(r"C:\Users\thaun\Downloads\MyanmarPhiksel_Fonts"),
        Path(r"C:\Users\thaun\Downloads\PadaukKyaungChee_Fonts"),
    ]

    for directory in directories:
        process_font_directory(directory)

    print("\nDone! All WOFF2 fonts converted to TTF.")
