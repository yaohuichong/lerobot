# -*- coding: utf-8 -*-
from __future__ import print_function

import codecs
import json
import os


def parse_joint_data(file_path):
    """Parse joint data file, return list of data lines"""
    data_lines = []
    with codecs.open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comment lines
            if not line or line.startswith("#"):
                continue
            data_lines.append(line)
    return data_lines


def extract_joint_values(line):
    """Extract joint values from data line"""
    parts = line.split(",")
    if len(parts) < 8:
        return None
    return {
        "timestamp": float(parts[0]),
        "step": int(parts[1]),
        "shoulder_pan": float(parts[2]),
        "shoulder_lift": float(parts[3]),
        "elbow_flex": float(parts[4]),
        "wrist_flex": float(parts[5]),
        "wrist_roll": float(parts[6]),
        "gripper": float(parts[7]),
    }


def get_joint_values_tuple(data):
    """Get joint values tuple (for comparison)"""
    return (
        data["shoulder_pan"],
        data["shoulder_lift"],
        data["elbow_flex"],
        data["wrist_flex"],
        data["wrist_roll"],
        data["gripper"],
    )


def extract_motion_segments(data_lines, static_threshold=10):
    """
    Extract motion segments, remove static parts
    When consecutive static_threshold frames have no change, it's considered static
    """
    # Parse all data
    parsed_data = []
    for line in data_lines:
        data = extract_joint_values(line)
        if data:
            parsed_data.append(data)

    if not parsed_data:
        return []

    # Mark each frame as static or not
    is_static = [False] * len(parsed_data)

    # Sliding window detection for static frames
    for i in range(len(parsed_data)):
        # Check consecutive 10 frames starting from current frame
        if i + static_threshold <= len(parsed_data):
            first_values = get_joint_values_tuple(parsed_data[i])
            is_all_same = True
            for j in range(1, static_threshold):
                current_values = get_joint_values_tuple(parsed_data[i + j])
                if first_values != current_values:
                    is_all_same = False
                    break
            if is_all_same:
                # Mark these 10 frames as static
                for j in range(static_threshold):
                    is_static[i + j] = True

    # Extract non-static segments
    motion_segments = []
    current_segment = []

    for i, data in enumerate(parsed_data):
        if not is_static[i]:
            current_segment.append(data)
        else:
            # Encounter static frame, save current segment if not empty
            if current_segment:
                motion_segments.append(current_segment)
                current_segment = []

    # Process last segment
    if current_segment:
        motion_segments.append(current_segment)

    return motion_segments


def process_file(input_file, output_dir):
    """Process single file"""
    # Parse data
    data_lines = parse_joint_data(input_file)

    # Extract motion segments
    motion_segments = extract_motion_segments(data_lines)

    # Merge all motion segments
    all_motion_data = []
    for segment in motion_segments:
        all_motion_data.extend(segment)

    # Generate output filename (replace .txt with .json)
    base_name = os.path.basename(input_file)
    output_name = base_name.replace(".txt", ".json")
    output_path = os.path.join(output_dir, output_name)

    # Save as JSON
    json_str = json.dumps(all_motion_data, indent=2, ensure_ascii=False)
    with codecs.open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    print("Processed: {}".format(base_name))
    print("  Original frames: {}".format(len(data_lines)))
    print("  Motion frames: {}".format(len(all_motion_data)))
    print("  Motion segments: {}".format(len(motion_segments)))
    print("  Output: {}".format(output_path))


def main():
    # Input directory
    input_dir = r"c:\Users\xuemu233\Desktop\lerobot\examples\joint_logs"

    # Get all txt files
    txt_files = [f for f in os.listdir(input_dir) if f.endswith(".txt")]

    print("Found {} txt files".format(len(txt_files)))
    print("-" * 50)

    for txt_file in txt_files:
        input_path = os.path.join(input_dir, txt_file)
        process_file(input_path, input_dir)
        print("-" * 50)

    print("\nAll files processed!")


if __name__ == "__main__":
    main()
