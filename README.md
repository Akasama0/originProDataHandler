# OriginPro Measurement Extractor

## Overview
This Python script automates the extraction of specific data columns (like Gate Voltage and Drain Current) from raw, unformatted instrument measurement files and exports them directly into an OriginLab Project (`.opju`). It is specifically designed to handle messy metadata headers, bypass CSV reading errors, and automatically format the Origin worksheets for immediate plotting.

## Requirements
To run this script, you must have a licensed, compatible version of Origin (2021 or later) installed on your Windows machine, along with the following Python packages:
* pandas
* originpro

You can install the required Python packages using pip:
`pip install pandas originpro`

## Usage
1. Open the script in your preferred Python editor.
2. Update the `raw_data_file` variable with the exact file path to your raw instrument CSV file.
3. Update the `opju_file_path` variable with your desired output directory and filename.
4. Run the script.

The script will pre-filter the raw data to bypass irregular metadata, search for the `DataName` and `DataValue` rows, extract the target columns, and save a fully formatted Origin project.

## Troubleshooting and Notes
* **File Paths:** Always use raw strings (e.g., `r"C:\path\to\file"`) in the script to prevent Windows backslash errors.
* **Column Names:** Python is case-sensitive. If your instrument saves columns as `Vg` or `V_G` instead of `VG`, you must update the `target_columns` list in the script to match the exact spelling output by your equipment.
* **Background Processes:** The script runs Origin invisibly to save resources. If the script crashes midway, check your Windows Task Manager for hidden `Origin.exe` processes and end them manually to free up memory.
