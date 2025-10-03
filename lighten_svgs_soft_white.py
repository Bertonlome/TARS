#!/usr/bin/env python3
"""
Enhanced SVG Color Batch Converter - Soft White Version
Converts dark SVG icons to soft white (#F7F7F7) versions for better dark theme contrast
This version uses a softer white that's easier on the eyes
"""

import os
import re
import shutil
from pathlib import Path

def lighten_svg_colors(svg_content):
    """Convert dark colors to soft white colors in SVG content - Enhanced version"""
    
    # Define comprehensive color mappings (dark and white -> soft white #F7F7F7)
    color_mappings = {
        # Pure white to soft white (convert existing white icons)
        r'fill="#ffffff"': 'fill="#F7F7F7"',
        r'fill="#fff"': 'fill="#F7F7F7"',
        r'stroke="#ffffff"': 'stroke="#F7F7F7"',
        r'stroke="#fff"': 'stroke="#F7F7F7"',
        
        # Pure black to soft white
        r'fill="#000000"': 'fill="#F7F7F7"',
        r'fill="#000"': 'fill="#F7F7F7"',
        r'stroke="#000000"': 'stroke="#F7F7F7"',
        r'stroke="#000"': 'stroke="#F7F7F7"',
        
        # All dark grays to soft white (comprehensive list)
        r'fill="#[0-7][0-7][0-7][0-7][0-7][0-7]"': 'fill="#F7F7F7"',  # Any 6-digit hex starting with 0-7
        r'stroke="#[0-7][0-7][0-7][0-7][0-7][0-7]"': 'stroke="#F7F7F7"',
        r'fill="#[0-7][0-7][0-7]"': 'fill="#F7F7F7"',  # Any 3-digit hex starting with 0-7
        r'stroke="#[0-7][0-7][0-7]"': 'stroke="#F7F7F7"',
        
        # Specific common dark colors
        r'fill="#333333"': 'fill="#F7F7F7"',
        r'fill="#333"': 'fill="#F7F7F7"',
        r'fill="#666666"': 'fill="#F7F7F7"',
        r'fill="#666"': 'fill="#F7F7F7"',
        r'fill="#999999"': 'fill="#F7F7F7"',
        r'fill="#999"': 'fill="#F7F7F7"',
        r'fill="#555555"': 'fill="#F7F7F7"',
        r'fill="#555"': 'fill="#F7F7F7"',
        r'fill="#777777"': 'fill="#F7F7F7"',
        r'fill="#777"': 'fill="#F7F7F7"',
        r'fill="#444444"': 'fill="#F7F7F7"',
        r'fill="#444"': 'fill="#F7F7F7"',
        r'fill="#222222"': 'fill="#F7F7F7"',
        r'fill="#222"': 'fill="#F7F7F7"',
        r'fill="#111111"': 'fill="#F7F7F7"',
        r'fill="#111"': 'fill="#F7F7F7"',
        
        # Stroke versions of the same
        r'stroke="#333333"': 'stroke="#F7F7F7"',
        r'stroke="#333"': 'stroke="#F7F7F7"',
        r'stroke="#666666"': 'stroke="#F7F7F7"',
        r'stroke="#666"': 'stroke="#F7F7F7"',
        r'stroke="#999999"': 'stroke="#F7F7F7"',
        r'stroke="#999"': 'stroke="#F7F7F7"',
        r'stroke="#555555"': 'stroke="#F7F7F7"',
        r'stroke="#555"': 'stroke="#F7F7F7"',
        r'stroke="#777777"': 'stroke="#F7F7F7"',
        r'stroke="#777"': 'stroke="#F7F7F7"',
        r'stroke="#444444"': 'stroke="#F7F7F7"',
        r'stroke="#444"': 'stroke="#F7F7F7"',
        r'stroke="#222222"': 'stroke="#F7F7F7"',
        r'stroke="#222"': 'stroke="#F7F7F7"',
        r'stroke="#111111"': 'stroke="#F7F7F7"',
        r'stroke="#111"': 'stroke="#F7F7F7"',
        
        # CSS style color definitions
        r'fill:\s*#000000': 'fill: #F7F7F7',
        r'fill:\s*#000': 'fill: #F7F7F7',
        r'stroke:\s*#000000': 'stroke: #F7F7F7',
        r'stroke:\s*#000': 'stroke: #F7F7F7',
        
        # CSS style with semicolon
        r'fill:\s*#000000;': 'fill: #F7F7F7;',
        r'fill:\s*#000;': 'fill: #F7F7F7;',
        r'stroke:\s*#000000;': 'stroke: #F7F7F7;',
        r'stroke:\s*#000;': 'stroke: #F7F7F7;'
    }
    
    # Apply color mappings
    modified_content = svg_content
    changes_made = False
    
    for pattern, replacement in color_mappings.items():
        if re.search(pattern, modified_content):
            modified_content = re.sub(pattern, replacement, modified_content)
            changes_made = True
    
    # Aggressive approach: Convert any RGB values where all components are < 128 to soft white
    def convert_hex_to_soft_white(match):
        hex_color = match.group(2)  # Get the hex color part (without #)
        
        # Validate hex color format
        if not re.match(r'^[0-9a-fA-F]+$', hex_color):
            return match.group(0)  # Return unchanged if invalid hex
            
        try:
            # Handle both 3-digit and 6-digit hex
            if len(hex_color) == 3:
                # Convert 3-digit to 6-digit
                r = int(hex_color[0], 16) * 17
                g = int(hex_color[1], 16) * 17
                b = int(hex_color[2], 16) * 17
            elif len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
            else:
                return match.group(0)  # Return unchanged if unexpected length
            
            # If all RGB components are dark (< 128), convert to soft white
            if r < 128 and g < 128 and b < 128:
                return match.group(0).replace(f"#{hex_color}", "#F7F7F7")
            return match.group(0)
        except ValueError:
            return match.group(0)  # Return unchanged if conversion fails
    
    # Apply aggressive hex color conversion
    # Match fill and stroke attributes with hex colors
    modified_content = re.sub(r'(fill|stroke)="(#[0-9a-fA-F]{3,6})"', 
                             lambda m: convert_hex_to_soft_white(m), 
                             modified_content)
    
    # Match CSS style hex colors
    modified_content = re.sub(r'(fill|stroke):\s*(#[0-9a-fA-F]{3,6})', 
                             lambda m: convert_hex_to_soft_white(m), 
                             modified_content)
    
    return modified_content

def process_svg_file(input_file, output_file=None, suffix="_soft_white"):
    """
    Process a single SVG file to convert dark colors to soft white.
    
    Args:
        input_file (Path): Input SVG file path
        output_file (Path): Output file path (optional)
        suffix (str): Suffix to add to output filename if output_file not specified
    
    Returns:
        Path: Path to the created output file, or None if failed
    """
    try:
        # Read the input SVG file
        with open(input_file, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        # Convert colors
        modified_content = lighten_svg_colors(svg_content)
        
        # Determine output filename
        if output_file is None:
            output_file = input_file.parent / f"{input_file.stem}{suffix}.svg"
        
        # Write the modified content
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        return output_file
        
    except Exception as e:
        print(f"Error processing {input_file}: {e}")
        return None

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert dark SVG icons to soft white (#F7F7F7) for dark themes')
    parser.add_argument('--source', '-s', default='.', help='Source directory (default: current directory)')
    parser.add_argument('--output', '-o', help='Output directory (default: same as source)')
    parser.add_argument('--suffix', default='_soft_white', help='Suffix for output files (default: _soft_white)')
    parser.add_argument('--pattern', default='*.svg', help='File pattern to match (default: *.svg)')
    parser.add_argument('--replace', action='store_true', help='Replace original files instead of creating new ones')
    
    args = parser.parse_args()
    
    source_dir = Path(args.source)
    output_dir = Path(args.output) if args.output else source_dir
    
    if not source_dir.exists():
        print(f"Error: Source directory '{source_dir}' does not exist")
        return
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all SVG files
    svg_files = list(source_dir.glob(args.pattern))
    
    if not svg_files:
        print(f"No SVG files found matching pattern '{args.pattern}' in '{source_dir}'")
        return
    
    print(f"Converting {len(svg_files)} SVG files to soft white (#F7F7F7)...")
    print(f"Source: {source_dir}")
    print(f"Output: {output_dir}")
    print(f"Replace mode: {'Yes' if args.replace else 'No'}")
    print()
    
    processed = 0
    errors = 0
    
    for svg_file in svg_files:
        # Skip files that already have the suffix to avoid double-processing
        if args.suffix in svg_file.stem and not args.replace:
            continue
            
        if args.replace:
            # Replace the original file
            output_file = svg_file
        else:
            # Create new file with suffix
            output_file = output_dir / f"{svg_file.stem}{args.suffix}.svg"
        
        result = process_svg_file(svg_file, output_file, args.suffix)
        
        if result:
            if args.replace:
                print(f"Processed: {svg_file.name}")
            else:
                print(f"Processed: {svg_file.name} -> {result.name}")
            processed += 1
        else:
            print(f"Failed: {svg_file.name}")
            errors += 1
    
    print()
    print("=" * 50)
    print(f"Processing complete!")
    print(f"Successfully processed: {processed} files")
    print(f"Errors: {errors} files")
    print(f"Output location: {output_dir}")
    
    if not args.replace:
        print(f"Original files preserved. New files have '{args.suffix}' suffix.")
    else:
        print("Original files have been replaced with soft white versions.")

if __name__ == "__main__":
    main()