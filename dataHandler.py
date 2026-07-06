import originpro as op
import pandas as pd
import csv
import os
import sys

# Known transfer-curve parameters -> (Origin long name, unit)
PARAM_INFO = {
    'VG': ('Gate Voltage', 'V'),
    'VD': ('Drain Voltage', 'V'),
    'ID': ('Drain Current', 'A'),
    'IG': ('Gate Current', 'A'),
    'gm': ('Transconductance', 'S'),
    'gmmax': ('Max Transconductance', 'S'),
    'dID': ('Delta ID', 'A'),
    'dVG': ('Delta VG', 'V'),
    'SS': ('Subthreshold Swing', 'V/dec'),
    'Imax': ('Max Current', 'A'),
    'Imin': ('Min Current', 'A'),
    'on-off': ('On/Off Ratio', ''),
    'SS_max': ('Max SS', 'V/dec'),
}

ALL_PARAMETERS = list(PARAM_INFO.keys())

DEFAULT_TARGET_COLUMNS = ['VG', 'ID']


def _extract_dataframe(raw_data_file, target_columns, log):
    """Read raw_data_file and return a DataFrame with just the chosen columns, or None on failure."""

    # 1. Use standard Python to pre-filter the file line-by-line
    filtered_rows = []
    try:
        with open(raw_data_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip completely empty lines
                if not row:
                    continue

                # Check if the first column is what we want
                first_col = str(row[0]).strip()
                if first_col in ['DataName', 'DataValue']:
                    filtered_rows.append(row)

    except Exception as e:
        log(f"Failed to read the file: {e}")
        return None

    if not filtered_rows:
        log("Error: Could not find any 'DataName' or 'DataValue' rows in the file.")
        return None

    # 2. Now hand the perfectly filtered rows to pandas
    # pandas will safely handle any remaining jagged edges by filling with NaN
    df_filtered = pd.DataFrame(filtered_rows)

    try:
        # 3. Extract the 'DataName' row to act as our column headers
        # Find the index of the first row containing 'DataName'
        header_idx = df_filtered[df_filtered[0] == 'DataName'].index[0]
        header_row = df_filtered.iloc[header_idx].tolist()

        # 4. Extract the 'DataValue' rows to act as our actual data
        df_data = df_filtered[df_filtered[0] == 'DataValue'].copy()

        # 5. Apply the headers to the data columns
        # We convert every header to a string and strip out any hidden leading/trailing spaces
        df_data.columns = [str(col).strip() for col in header_row]

        # DEBUGGING: Print the exact names found so you know what is available
        log(f"--> Available columns found in your file: {df_data.columns.tolist()}")

        # 6. Clean up: Drop the 'DataName' label column and convert strings to numbers
        # Because we stripped spaces, we can safely drop the column named 'DataName'
        if 'DataName' in df_data.columns:
            df_data = df_data.drop(columns=['DataName'])

        df_data = df_data.apply(pd.to_numeric, errors='coerce')

        # 7. Extract the parameter columns the user chose

        # Double-check that our targets actually exist before extracting
        missing_cols = [col for col in target_columns if col not in df_data.columns]
        if missing_cols:
            log(f"--> ERROR: Still missing these columns: {missing_cols}")
            log("--> Please check the exact spelling against the printed available columns.")
            return None

        # reset_index so files with different row counts/gaps still line up positionally
        return df_data[target_columns].dropna().reset_index(drop=True)

    except KeyError as e:
        log(f"Error: Could not find the requested columns. Check the exact spelling in your DataName row. {e}")
        return None
    except Exception as e:
        log(f"Failed to clean data: {e}")
        return None


def process_file(raw_data_file, opju_file_path, target_columns=None, log=print):
    """Read raw_data_file, extract the chosen parameter columns, and save an Origin project to opju_file_path."""

    if not target_columns:
        target_columns = DEFAULT_TARGET_COLUMNS

    # Set Origin to run invisibly
    op.set_show(False)

    log("Reading and cleaning raw measurement file...")

    df_extracted = _extract_dataframe(raw_data_file, target_columns, log)
    if df_extracted is None:
        return False

    # --- Origin Export Section ---
    try:
        op.new()
        wks = op.new_sheet()
        wks.name = "Extracted_Data"

        log("Pushing extracted data to Origin...")
        wks.from_df(df_extracted)

        # 10. Configure Origin Columns correctly using originpro methods
        # 'L' stands for Long Name, 'U' stands for Units
        long_names = [PARAM_INFO.get(col, (col, ''))[0] for col in target_columns]
        units = [PARAM_INFO.get(col, (col, ''))[1] for col in target_columns]
        wks.set_labels(long_names, 'L')
        wks.set_labels(units, 'U')

        # Set the column designations (first selected column to X, the rest to Y)
        axis_designation = 'x' + 'y' * (len(target_columns) - 1) if len(target_columns) > 1 else 'y'
        wks.cols_axis(axis_designation)

        # 11. Save the Origin Project
        log(f"Saving project to {opju_file_path}...")
        op.save(opju_file_path)
        log("Extraction and conversion completed successfully!")
        return True

    except Exception as e:
        log(f"An error occurred in Origin: {e}")
        return False

    finally:
        # Exit Origin to free up resources
        if op and op.oext:
            op.exit()


def process_folder(input_folder, opju_file_path, target_columns=None, log=print):
    """Extract the chosen columns from every CSV file in input_folder and lay them out
    side by side (laterally concatenated) in a single worksheet of one Origin project,
    saved to opju_file_path.

    Returns (success_count, failure_count, saved) where saved indicates whether the
    combined project was written out.
    """

    if not target_columns:
        target_columns = DEFAULT_TARGET_COLUMNS

    csv_files = sorted(
        f for f in os.listdir(input_folder)
        if f.lower().endswith('.csv') and os.path.isfile(os.path.join(input_folder, f))
    )

    if not csv_files:
        log(f"No CSV files found in {input_folder}")
        return 0, 0, False

    op.set_show(False)

    frames = []
    file_names = []
    success_count = 0
    failure_count = 0

    for i, filename in enumerate(csv_files, start=1):
        raw_data_file = os.path.join(input_folder, filename)
        log(f"[{i}/{len(csv_files)}] Reading {filename}...")

        try:
            df_extracted = _extract_dataframe(raw_data_file, target_columns, log)
        except Exception as e:
            log(f"Unexpected error while processing {filename}: {e}")
            df_extracted = None

        if df_extracted is None:
            log(f"--> Skipped {filename} due to the error above.")
            failure_count += 1
            continue

        # Give each file's block of columns a unique, Origin-safe short name;
        # the original filename is kept in the Comments row for traceability.
        df_extracted = df_extracted.copy()
        df_extracted.columns = [f"F{i}_{col}" for col in target_columns]

        frames.append(df_extracted)
        file_names.append(os.path.splitext(filename)[0])
        success_count += 1

    if not frames:
        log("No files were successfully processed; nothing to save.")
        return success_count, failure_count, False

    log("Concatenating extracted data laterally...")
    combined_df = pd.concat(frames, axis=1)

    long_names = []
    units = []
    comments = []
    for base_name in file_names:
        for col in target_columns:
            desc, unit = PARAM_INFO.get(col, (col, ''))
            long_names.append(desc)
            units.append(unit)
            comments.append(base_name)

    saved = False
    try:
        op.new()
        wks = op.new_sheet()
        wks.name = "Batch_Extracted_Data"

        log("Pushing combined data to Origin...")
        wks.from_df(combined_df)

        # 'L' = Long Name, 'U' = Units, 'C' = Comments (holds the source filename)
        wks.set_labels(long_names, 'L')
        wks.set_labels(units, 'U')
        wks.set_labels(comments, 'C')

        # Repeat the x/y pattern for each file's block of columns
        block_axis = 'x' + 'y' * (len(target_columns) - 1) if len(target_columns) > 1 else 'y'
        wks.cols_axis(block_axis * len(frames))

        log(f"Saving project to {opju_file_path}...")
        op.save(opju_file_path)
        saved = True

    except Exception as e:
        log(f"An error occurred in Origin: {e}")

    finally:
        if op and op.oext:
            op.exit()

    log(f"Batch complete: {success_count} succeeded, {failure_count} failed out of {len(csv_files)} file(s).")
    return success_count, failure_count, saved


if __name__ == "__main__":
    # Define file paths (Use raw strings 'r' to handle Windows backslashes)
    raw_data_file = r"C:\Users\Akasa\保存\研究\kanta_cv\60s30s\半パラ\20260706mobility\Transfer VDS=0.1V [60s30s1151(3) ; 2026_07_06 9_02_48].csv"
    opju_file_path = r"C:\Users\Akasa\保存\研究\kanta_cv\60s30s\20260706transfer.opju"

    if not process_file(raw_data_file, opju_file_path):
        sys.exit(1)
