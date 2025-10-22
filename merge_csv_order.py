#!/usr/bin/env python3
"""
Merge CSV files: Take row order from correct_order.csv and add new columns from new_columns.csv
"""

import csv
import sys

def merge_csv_files(correct_order_path, new_columns_path, output_path, target_columns):
    """
    Merge two CSV files:
    - Use row order from correct_order_path
    - Use column data from new_columns_path
    - Output only columns specified in target_columns
    
    Rows are matched by composite key: (Procedure, Task Object)
    Note: Value field can change, so we don't use it in the key
    """
    
    print(f"Reading data from: {new_columns_path}")
    # Read the file with new columns into a dictionary keyed by composite key (Procedure, Task Object, Value)
    new_data = {}
    with open(new_columns_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (
                row.get('Procedure', '').strip(),
                row.get('Task Object', '').strip(),
                row.get('Value', '').strip()
            )
            new_data[key] = row
    print(f"  Found {len(new_data)} rows")

    # Read correct order
    print(f"\nReading correct order from: {correct_order_path}")
    correct_order_keys = []
    with open(correct_order_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (
                row.get('Procedure', '').strip(),
                row.get('Task Object', '').strip(),
                row.get('Value', '').strip()
            )
            correct_order_keys.append(key)
    print(f"  Found {len(correct_order_keys)} rows")
    
    # Use target columns for output
    output_columns = target_columns
    print(f"\nOutput will have {len(output_columns)} columns: {output_columns}")
    
    print(f"\nMerging and writing to: {output_path}")
    matched_count = 0
    unmatched_count = 0
    
    with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=output_columns)
        writer.writeheader()
        for key in correct_order_keys:
            # Look up matching row in new_data
            if key in new_data:
                source_row = new_data[key]
                output_row = {col: source_row.get(col, '') for col in output_columns}
                writer.writerow(output_row)
                matched_count += 1
            else:
                # No match found - create empty row
                output_row = {col: '' for col in output_columns}
                output_row['Procedure'] = key[0]
                output_row['Task Object'] = key[1]
                output_row['Value'] = key[2]
                writer.writerow(output_row)
                unmatched_count += 1
                print(f"  Warning: No match found for key {key}")
    
    print(f"\nMerge complete!")
    print(f"  Matched rows: {matched_count}")
    print(f"  Unmatched rows: {unmatched_count}")
    print(f"  Output written to: {output_path}")

if __name__ == '__main__':
    # File paths
    correct_order_file = 'IA_updated.csv'  # Ground truth for correct order
    new_columns_file = 'Core/briefing_export_HIGH_LOA_BACKUP.csv'  # Has correct columns and data (but wrong order)
    output_file = 'Core/briefing_export_HIGH_LOA_FIXED.csv'
    
    # Define the exact columns we want in the output (from the BACKUP file structure)
    target_columns = [
        'Procedure', 'Classification', 'Type', 'Category', 'Task Object', 'Value',
        'Human Role', 'Autonomy Role', 'Information Requirement',
        'Constraint Type', 'Time constraint (in s)', 'Execution Type',
        'interaction', 'Time to Initiate Action', 'Time after Ending Action', 'Callout',
        'Condition Type', 'Condition Function', 'Monitor Scope'
    ]
    
    print("=" * 60)
    print("CSV Merge Tool: Restore correct row order + keep new columns")
    print("=" * 60)
    
    merge_csv_files(correct_order_file, new_columns_file, output_file, target_columns)
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("1. Review the output file: Core/briefing_export_HIGH_LOA_FIXED.csv")
    print("2. If correct, rename it to replace the original:")
    print("   mv Core/briefing_export_HIGH_LOA_FIXED.csv Core/briefing_export_HIGH_LOA.csv")
    print("=" * 60)
