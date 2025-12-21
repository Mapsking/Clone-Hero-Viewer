import os
import configparser
import re
from PIL import Image
import json
import subprocess

# -------------------------
# ANSI color codes
# -------------------------
T_COLOR = "\033[92m"
A_COLOR = "\033[94m"
B_COLOR = "\033[96m"
SCANNED_COUNT_COLOR = "\033[35m"
ERROR_COUNT_COLOR = "\033[31m"
WARNING_COUNT_COLOR = "\033[33m"
ERROR_HEADER_COLOR = "\033[41m"
WARNING_HEADER_COLOR = "\033[43m"
ERROR_FILE_COLOR = "\033[92m"
WARNING_FILE_COLOR = "\033[92m"
ERROR_DESC_COLOR = "\033[34m"
WARNING_DESC_COLOR = "\033[34m"
FIELD_COLOR = "\033[93m"
RESET = "\033[0m"

# -------------------------
# Read folder paths from config.txt
# -------------------------
config_file = "config.txt"
paths = {}

with open(config_file, "r", encoding="utf-8") as f:
    for line in f:
        if "=" in line:
            key, value = line.strip().split("=", 1)
            paths[key.strip()] = value.strip()

# -------------------------
# Prompt which folder(s) to scan
# -------------------------
def choose_folder():
    while True:
        choice = input(f"Scan Test ({T_COLOR}T{RESET}), Actual ({A_COLOR}A{RESET}), or Both ({B_COLOR}B{RESET})? ").strip().upper()
        if choice in ['T', 'A', 'B']:
            return choice
        print("Invalid choice, please enter T, A, or B.")

scan_choice = choose_folder()

folders_to_scan = []
if scan_choice == 'T':
    folders_to_scan.append(paths.get("color_profiles_test"))
elif scan_choice == 'A':
    folders_to_scan.append(paths.get("color_profiles_actual"))
else:
    folders_to_scan.extend([paths.get("color_profiles_test"), paths.get("color_profiles_actual")])
    
highway_folders_to_scan = []
if scan_choice == 'T':
    highway_folders_to_scan.append(paths.get("highways_test"))
elif scan_choice == 'A':
    highway_folders_to_scan.append(paths.get("highways_actual"))
else:
    highway_folders_to_scan.extend([paths.get("highways_test"), paths.get("highways_actual")])
    

print(f"\nScanning {'Test' if scan_choice=='T' else 'Actual' if scan_choice=='A' else 'Both'} folder(s)...\n")

# -------------------------
# Recursively get files
# -------------------------
def get_files_recursive(folder, extensions):
    file_list = []
    if not folder:
        return file_list
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith(extensions):
                file_list.append(os.path.join(root, file))
    return sorted(file_list, key=lambda x: os.path.basename(x).lower())

ini_files = []
for folder in folders_to_scan:
    ini_files.extend(get_files_recursive(folder, (".ini",)))

highway_files = []
for folder in highway_folders_to_scan:
    highway_files.extend(get_files_recursive(folder, (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG")))
    
thumbnail_folder = os.path.join("docs", "thumbnails")
os.makedirs(thumbnail_folder, exist_ok=True)

thumbnails_info = []

# Clear existing thumbnails to keep folder in sync
for existing_file in os.listdir(thumbnail_folder):
    file_path = os.path.join(thumbnail_folder, existing_file)
    if os.path.isfile(file_path):
        os.remove(file_path)

for file_path in highway_files:
    try:
        with Image.open(file_path) as img:
            img.thumbnail((300, 300))  # max width/height 300px
            base_name = os.path.basename(file_path)
            thumb_path = os.path.join(thumbnail_folder, base_name)
            img.save(thumb_path)
            thumb_web_path = os.path.join("thumbnails", base_name).replace("\\", "/")
            thumbnails_info.append({"file": base_name, "thumbnail": thumb_web_path})
    except Exception as e:
        print(f"Error creating thumbnail for {file_path}: {e}")

# -------------------------
# Fields and regex
# -------------------------
ERROR_FIELDS = [
    'note_green', 'note_red', 'note_yellow',
    'note_blue', 'note_orange', 'note_sp_active', 'note_open'
]
HEX_REGEX = re.compile(r'^#[0-9A-Fa-f]{6}$')

# -------------------------
# Scan ini files
# -------------------------
errors_dict = {}
warnings_dict = {}

for ini_file in ini_files:
    config = configparser.ConfigParser()
    try:
        config.read(ini_file)
    except Exception as e:
        warnings_dict.setdefault(os.path.basename(ini_file), []).append(f"Parse error: {str(e)}")
        continue

    file_errors = {}
    file_warnings = {}

    # Check errors (7 fields)
    for field in ERROR_FIELDS:
        found = False
        for section in config.sections():
            if field in config[section]:
                found = True
                value = config[section][field].strip()
                if not HEX_REGEX.match(value):
                    file_errors.setdefault("Invalid Hex Code Value", []).append(field)
                break
        if not found:
            file_errors.setdefault("Missing Required Field", []).append(field)

    # Check warnings (all other fields)
    for section in config.sections():
        for key, value in config[section].items():
            if key not in ERROR_FIELDS:
                value = value.strip()
                if value and not HEX_REGEX.match(value):
                    file_warnings.setdefault("Invalid Hex Code Value", []).append(key)

    if file_errors:
        errors_dict[os.path.basename(ini_file)] = file_errors
    if file_warnings:
        warnings_dict[os.path.basename(ini_file)] = file_warnings

# -------------------------
# Output summary
# -------------------------
print(
    f"Scanned {SCANNED_COUNT_COLOR}{len(ini_files):,}{RESET} color profiles "
    f"and {SCANNED_COUNT_COLOR}{len(highway_files):,}{RESET} highway images."
)
print(
    f"Generated {SCANNED_COUNT_COLOR}{len(thumbnails_info):,}{RESET} highway thumbnails.\n"
)

# Calculate counts
total_errors = sum(len(v) for file in errors_dict.values() for v in file.values())
total_warnings = sum(len(v) for file in warnings_dict.values() for v in file.values())

print(f"Found {ERROR_COUNT_COLOR}{total_errors}{RESET} errors and {WARNING_COUNT_COLOR}{total_warnings}{RESET} warnings:\n")

# Errors
if errors_dict:
    print(f"{ERROR_HEADER_COLOR}Errors:{RESET}")
    for fname, error_entries in errors_dict.items():
        print(f"{ERROR_FILE_COLOR}{fname}:{RESET}")
        for category, fields in error_entries.items():
            print(f"    {ERROR_DESC_COLOR}{category}:{RESET}")
            # for f in fields:
                # print(f"        {FIELD_COLOR}{f}{RESET}")
        print()  # blank line after each file

# Warnings
if warnings_dict:
    print(f"{WARNING_HEADER_COLOR}Warnings:{RESET}")
    for fname, warning_entries in warnings_dict.items():
        print(f"{WARNING_FILE_COLOR}{fname}:{RESET}")
        for category, fields in warning_entries.items():
            print(f"    {WARNING_DESC_COLOR}{category}:{RESET}")
            # for f in fields:
                # print(f"        {FIELD_COLOR}{f}{RESET}")
        print()  # blank line after each file

from datetime import datetime

summary_path = os.path.join("output", "scan_summary.txt")

os.makedirs("output", exist_ok=True)

with open(summary_path, "w", encoding="utf-8") as f:
    f.write(f"Scan completed: {datetime.now()}\n")
    f.write(f"Highways processed: {len(highway_files)}\n")
    f.write(f"Color profiles processed: {len(ini_files)}\n")

json_summary = {
    "timestamp": str(datetime.now()),
    "highways": [os.path.basename(f) for f in highway_files],
    "color_profiles": [os.path.basename(f) for f in ini_files],
    "thumbnails": thumbnails_info,
    "errors": errors_dict,
    "warnings": warnings_dict
}

os.makedirs("docs", exist_ok=True)
json_path = os.path.join("docs", "scan_summary.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json_summary, f, indent=4)

def git_push_changes(commit_message="Update site from scan"):
    try:
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Changes pushed to GitHub successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")

git_push_changes()