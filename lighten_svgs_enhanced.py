#!/usr/bin/env python3
"""
Enhanced SVG Color Batch Converter
Converts dark SVG icons to light/white versions for dark themes
This version is more aggressive and handles various shades of dark colors
"""

import os
import re
import shutil
from pathlib import Path

def lighten_svg_colors(svg_content):
    """Convert dark colors to light colors in SVG content - Enhanced version"""
    
    # First, let's inspect what colors are actually being used
    def find_colors(content):
        """Find all color values in the SVG"""
        color_patterns = [
            r'fill="(#[0-9a-fA-F]{3,6})"',
            r'stroke="(#[0-9a-fA-F]{3,6})"',
            r'fill:\s*(#[0-9a-fA-F]{3,6})',
            r'stroke:\s*(#[0-9a-fA-F]{3,6})',
        ]
        colors = set()
        for pattern in color_patterns:
            matches = re.findall(pattern, content)
            colors.update(matches)
        return colors
    
    # Define comprehensive color mappings (dark -> light)
    color_mappings = {
        # Pure black to white
        r'fill="#000000"': 'fill="#ffffff"',
        r'fill="#000"': 'fill="#fff"',
        r'stroke="#000000"': 'stroke="#ffffff"',
        r'stroke="#000"': 'stroke="#fff"',
        
        # All dark grays to white (comprehensive list)
        r'fill="#[0-7][0-7][0-7][0-7][0-7][0-7]"': 'fill="#ffffff"',  # Any 6-digit hex starting with 0-7
        r'stroke="#[0-7][0-7][0-7][0-7][0-7][0-7]"': 'stroke="#ffffff"',
        r'fill="#[0-7][0-7][0-7]"': 'fill="#fff"',  # Any 3-digit hex starting with 0-7
        r'stroke="#[0-7][0-7][0-7]"': 'stroke="#fff"',
        
        # Specific common dark colors
        r'fill="#333333"': 'fill="#ffffff"',
        r'fill="#333"': 'fill="#fff"',
        r'fill="#666666"': 'fill="#ffffff"',
        r'fill="#666"': 'fill="#fff"',
        r'fill="#999999"': 'fill="#ffffff"',
        r'fill="#999"': 'fill="#fff"',
        r'fill="#555555"': 'fill="#ffffff"',
        r'fill="#555"': 'fill="#fff"',
        r'fill="#777777"': 'fill="#ffffff"',
        r'fill="#777"': 'fill="#fff"',
        r'fill="#444444"': 'fill="#ffffff"',
        r'fill="#444"': 'fill="#fff"',
        r'fill="#222222"': 'fill="#ffffff"',
        r'fill="#222"': 'fill="#fff"',
        r'fill="#111111"': 'fill="#ffffff"',
        r'fill="#111"': 'fill="#fff"',
        
        # Stroke versions of the same
        r'stroke="#333333"': 'stroke="#ffffff"',
        r'stroke="#333"': 'stroke="#fff"',
        r'stroke="#666666"': 'stroke="#ffffff"',
        r'stroke="#666"': 'stroke="#fff"',
        r'stroke="#999999"': 'stroke="#ffffff"',
        r'stroke="#999"': 'stroke="#fff"',
        r'stroke="#555555"': 'stroke="#ffffff"',
        r'stroke="#555"': 'stroke="#fff"',
        r'stroke="#777777"': 'stroke="#ffffff"',
        r'stroke="#777"': 'stroke="#fff"',
        r'stroke="#444444"': 'stroke="#ffffff"',
        r'stroke="#444"': 'stroke="#fff"',
        r'stroke="#222222"': 'stroke="#ffffff"',
        r'stroke="#222"': 'stroke="#fff"',
        r'stroke="#111111"': 'stroke="#ffffff"',
        r'stroke="#111"': 'stroke="#fff"',
        
        # Named colors
        r'fill="black"': 'fill="white"',
        r'stroke="black"': 'stroke="white"',
        r'fill="darkgray"': 'fill="white"',
        r'fill="darkgrey"': 'fill="white"',
        r'fill="gray"': 'fill="white"',
        r'fill="grey"': 'fill="white"',
        r'stroke="darkgray"': 'stroke="white"',
        r'stroke="darkgrey"': 'stroke="white"',
        r'stroke="gray"': 'stroke="white"',
        r'stroke="grey"': 'stroke="white"',
        
        # CSS style attributes (comprehensive)
        r'fill:\s*#000000': 'fill: #ffffff',
        r'fill:\s*#000': 'fill: #fff',
        r'fill:\s*black': 'fill: white',
        r'fill:\s*#333333': 'fill: #ffffff',
        r'fill:\s*#333': 'fill: #fff',
        r'fill:\s*#666666': 'fill: #ffffff',
        r'fill:\s*#666': 'fill: #fff',
        r'fill:\s*#555555': 'fill: #ffffff',
        r'fill:\s*#555': 'fill: #fff',
        r'fill:\s*#777777': 'fill: #ffffff',
        r'fill:\s*#777': 'fill: #fff',
        r'fill:\s*#444444': 'fill: #ffffff',
        r'fill:\s*#444': 'fill: #fff',
        r'fill:\s*#222222': 'fill: #ffffff',
        r'fill:\s*#222': 'fill: #fff',
        r'fill:\s*#111111': 'fill: #ffffff',
        r'fill:\s*#111': 'fill: #fff',
        
        r'stroke:\s*#000000': 'stroke: #ffffff',
        r'stroke:\s*#000': 'stroke: #fff',
        r'stroke:\s*black': 'stroke: white',
        r'stroke:\s*#333333': 'stroke: #ffffff',
        r'stroke:\s*#333': 'stroke: #fff',
        r'stroke:\s*#666666': 'stroke: #ffffff',
        r'stroke:\s*#666': 'stroke: #fff',
        r'stroke:\s*#555555': 'stroke: #ffffff',
        r'stroke:\s*#555': 'stroke: #fff',
        r'stroke:\s*#777777': 'stroke: #ffffff',
        r'stroke:\s*#777': 'stroke: #fff',
        r'stroke:\s*#444444': 'stroke: #ffffff',
        r'stroke:\s*#444': 'stroke: #fff',
        r'stroke:\s*#222222': 'stroke: #ffffff',
        r'stroke:\s*#222': 'stroke: #fff',
        r'stroke:\s*#111111': 'stroke: #ffffff',
        r'stroke:\s*#111': 'stroke: #fff',
    }
    
    # Apply all color mappings
    original_content = svg_content
    for dark_pattern, light_replacement in color_mappings.items():
        svg_content = re.sub(dark_pattern, light_replacement, svg_content, flags=re.IGNORECASE)
    
    # Additional aggressive approach: convert any dark color (RGB values < 128) to white
    def convert_hex_to_white(match):
        hex_color = match.group(1)
        if len(hex_color) == 3:
            # Convert 3-digit hex to 6-digit
            r, g, b = hex_color[0], hex_color[1], hex_color[2]
            hex_color = r+r + g+g + b+b
        
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16) 
            b = int(hex_color[4:6], 16)
            
            # If all RGB values are dark (< 128), convert to white
            if r < 128 and g < 128 and b < 128:
                return match.group(0).replace(hex_color, 'ffffff')
        except:
            pass
        
        return match.group(0)
    
    # Apply the aggressive hex conversion
    svg_content = re.sub(r'(fill|stroke)="(#[0-9a-fA-F]{3,6})"', 
                        lambda m: convert_hex_to_white(m), svg_content)
    svg_content = re.sub(r'(fill|stroke):\s*(#[0-9a-fA-F]{3,6})', 
                        lambda m: convert_hex_to_white(m), svg_content)
    
    return svg_content

def process_svg_files(source_dir, output_dir=None, suffix="_white", preview_only=False):
    """Process all SVG files in a directory"""
    
    source_path = Path(source_dir)
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
    else:
        output_path = source_path
    
    svg_files = list(source_path.glob("*.svg"))
    
    if not svg_files:
        print(f"No SVG files found in {source_dir}")
        return
    
    print(f"Found {len(svg_files)} SVG files")
    
    for svg_file in svg_files:
        try:
            # Read original SVG
            with open(svg_file, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Convert colors
            lightened_content = lighten_svg_colors(original_content)
            
            # Check if any changes were made
            if original_content == lightened_content:
                if preview_only:
                    print(f"No changes needed: {svg_file.name}")
                continue
            
            # Determine output filename
            if output_dir or suffix:
                if suffix and not svg_file.stem.endswith(suffix):
                    output_filename = f"{svg_file.stem}{suffix}.svg"
                else:
                    output_filename = svg_file.name
                output_file = output_path / output_filename
            else:
                output_file = svg_file
            
            if preview_only:
                print(f"Would process: {svg_file.name} -> {output_file.name}")
            else:
                # Backup original if overwriting
                if output_file == svg_file:
                    backup_file = svg_file.with_suffix('.svg.backup')
                    if not backup_file.exists():
                        shutil.copy2(svg_file, backup_file)
                        print(f"Backed up: {svg_file.name} -> {backup_file.name}")
                
                # Write lightened SVG
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(lightened_content)
                
                print(f"Processed: {svg_file.name} -> {output_file.name}")
                
        except Exception as e:
            print(f"Error processing {svg_file.name}: {e}")

if __name__ == "__main__":
    import sys
    
    # Default settings
    source_directory = "."
    output_directory = None
    suffix = "_white"
    preview = False
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("""
Usage: python lighten_svgs_enhanced.py [options]

Options:
  --preview          Show what would be done without making changes
  --suffix SUFFIX    Add suffix to output files (default: _white)
  --no-suffix        Don't add suffix (overwrite originals with backup)
  --output DIR       Save to different directory
  --source DIR       Source directory (default: current)

Examples:
  python lighten_svgs_enhanced.py --preview
  python lighten_svgs_enhanced.py --no-suffix
  python lighten_svgs_enhanced.py --output ../icons_white
  python lighten_svgs_enhanced.py --source images/icons --suffix _light
            """)
            sys.exit(0)
        
        # Parse arguments
        i = 1
        while i < len(sys.argv):
            if sys.argv[i] == "--preview":
                preview = True
            elif sys.argv[i] == "--no-suffix":
                suffix = ""
            elif sys.argv[i] == "--suffix" and i + 1 < len(sys.argv):
                suffix = sys.argv[i + 1]
                i += 1
            elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_directory = sys.argv[i + 1]
                i += 1
            elif sys.argv[i] == "--source" and i + 1 < len(sys.argv):
                source_directory = sys.argv[i + 1]
                i += 1
            i += 1
    
    print(f"Enhanced SVG Lightener")
    print(f"Source: {source_directory}")
    print(f"Output: {output_directory or 'same as source'}")
    print(f"Suffix: '{suffix}'" if suffix else "No suffix (will overwrite)")
    print(f"Mode: {'Preview only' if preview else 'Processing files'}")
    print("-" * 50)
    
    process_svg_files(
        source_dir=source_directory,
        output_dir=output_directory, 
        suffix=suffix,
        preview_only=preview
    )