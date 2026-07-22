import originpro as op
import pandas as pd
import csv
import os
import sys

# Known transfer-curve parameters -> (Origin long name, unit)
# Units for the width-normalized parameters already reflect the mA/mm or mS/mm
# they get converted to (see PER_WIDTH_PARAMS / _apply_width_normalization).
PARAM_INFO = {
    'VG': ('Gate Voltage', 'V'),
    'VD': ('Drain Voltage', 'V'),
    'ID': ('Drain Current', 'mA/mm'),
    'IG': ('Gate Current', 'mA/mm'),
    'gm': ('Transconductance', 'mS/mm'),
    'gmmax': ('Max Transconductance', 'mS/mm'),
    'dID': ('Delta ID', 'mA/mm'),
    'dVG': ('Delta VG', 'V'),
    'SS': ('Subthreshold Swing', 'V/dec'),
    'Imax': ('Max Current', 'mA/mm'),
    'Imin': ('Min Current', 'mA/mm'),
    'on-off': ('On/Off Ratio', ''),
    'SS_max': ('Max SS', 'V/dec'),
}

ALL_PARAMETERS = list(PARAM_INFO.keys())

DEFAULT_TARGET_COLUMNS = ['VG', 'ID']

# Output (VD-ID) characteristic files only ever record these two swept quantities.
OUTPUT_COLUMNS = ['VD', 'ID']

# Raw data for these comes in A (currents) or S (transconductance); they get
# scaled by 1000/width_mm to become mA/mm or mS/mm, normalizing by channel width.
PER_WIDTH_PARAMS = {'ID', 'IG', 'dID', 'Imax', 'Imin', 'gm', 'gmmax'}


def _apply_width_normalization(df, target_columns, width_mm, log):
    """Scale the raw A/S columns in-place to mA/mm or mS/mm. Returns False on error."""

    convert_cols = [col for col in target_columns if col in PER_WIDTH_PARAMS]
    if not convert_cols:
        return True

    if not width_mm:
        log(
            f"--> ERROR: Channel width (mm) is required to convert {convert_cols} "
            "to mA/mm or mS/mm."
        )
        return False

    for col in convert_cols:
        df[col] = df[col] * 1000.0 / width_mm

    return True


def _read_rows(raw_data_file, log):
    """Read the raw CSV into a plain list of rows (small file, kept in memory for reuse)."""
    try:
        with open(raw_data_file, 'r', encoding='utf-8-sig') as f:
            return [row for row in csv.reader(f) if row]
    except Exception as e:
        log(f"Failed to read the file: {e}")
        return None


def _get_test_parameter(rows, key):
    """Find a 'TestParameter, <key>, <values...>' row and return its values as strings, or None."""
    for row in rows:
        if len(row) >= 2 and row[0].strip() == 'TestParameter' and row[1].strip() == key:
            return [v.strip() for v in row[2:]]
    return None


def _detect_measurement_type(rows):
    """Return 'output', 'transfer', or 'unknown' based on the file's SetupTitle row."""
    for row in rows:
        if len(row) >= 2 and row[0].strip() == 'SetupTitle':
            title = row[1].strip().lower()
            if title.startswith('output'):
                return 'output'
            if title.startswith('transfer'):
                return 'transfer'
    return 'unknown'


def _dataname_datavalue_df(rows, log):
    """Build the numeric DataName/DataValue-tagged DataFrame (all columns) from raw rows."""
    filtered_rows = [row for row in rows if str(row[0]).strip() in ('DataName', 'DataValue')]

    if not filtered_rows:
        log("Error: Could not find any 'DataName' or 'DataValue' rows in the file.")
        return None

    # pandas will safely handle any remaining jagged edges by filling with NaN
    df_filtered = pd.DataFrame(filtered_rows)

    try:
        # Find the 'DataName' row to act as our column headers
        header_idx = df_filtered[df_filtered[0] == 'DataName'].index[0]
        header_row = df_filtered.iloc[header_idx].tolist()

        # Extract the 'DataValue' rows to act as our actual data
        df_data = df_filtered[df_filtered[0] == 'DataValue'].copy()

        # Apply the headers to the data columns, stripping hidden leading/trailing spaces
        df_data.columns = [str(col).strip() for col in header_row]

        # DEBUGGING: Print the exact names found so you know what is available
        log(f"--> Available columns found in your file: {df_data.columns.tolist()}")

        if 'DataName' in df_data.columns:
            df_data = df_data.drop(columns=['DataName'])

        return df_data.apply(pd.to_numeric, errors='coerce')

    except KeyError as e:
        log(f"Error: Could not find the requested columns. Check the exact spelling in your DataName row. {e}")
        return None
    except Exception as e:
        log(f"Failed to clean data: {e}")
        return None


def _extract_dataframe(rows, target_columns, log, width_mm=None):
    """Return a DataFrame with just the chosen columns from already-read rows, or None on failure."""

    df_data = _dataname_datavalue_df(rows, log)
    if df_data is None:
        return None

    # Double-check that our targets actually exist before extracting
    missing_cols = [col for col in target_columns if col not in df_data.columns]
    if missing_cols:
        log(f"--> ERROR: Still missing these columns: {missing_cols}")
        log("--> Please check the exact spelling against the printed available columns.")
        return None

    # reset_index so files with different row counts/gaps still line up positionally
    df_extracted = df_data[target_columns].dropna().reset_index(drop=True)

    if not _apply_width_normalization(df_extracted, target_columns, width_mm, log):
        return None

    return df_extracted


def _format_vg(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def _extract_output_sets(rows, log, width_mm=None):
    """Split an Output (VD-ID) file's repeated VD sweep into one set per VG step.

    The instrument records one VG sweep after another stacked in the same VD/ID
    columns (Measurement.Secondary.* says how many steps and at what VG values).

    Returns a list of (vg_value, df_chunk) tuples, or None on failure.
    """

    df_extracted = _extract_dataframe(rows, OUTPUT_COLUMNS, log, width_mm)
    if df_extracted is None:
        return None

    secondary_start = _get_test_parameter(rows, 'Measurement.Secondary.Start')
    secondary_count = _get_test_parameter(rows, 'Measurement.Secondary.Count')
    secondary_step = _get_test_parameter(rows, 'Measurement.Secondary.Step')

    if not secondary_start or not secondary_count or not secondary_step:
        log("--> ERROR: Could not find Measurement.Secondary.Start/Count/Step to split VG sets.")
        return None

    try:
        vg_start = float(secondary_start[0])
        num_sets = int(float(secondary_count[0]))
        vg_step = float(secondary_step[0])
    except (ValueError, IndexError) as e:
        log(f"--> ERROR: Could not parse Secondary sweep parameters: {e}")
        return None

    total_rows = len(df_extracted)
    if num_sets <= 0 or total_rows % num_sets != 0:
        log(
            f"--> ERROR: {total_rows} data rows do not divide evenly into "
            f"{num_sets} VG set(s); cannot split."
        )
        return None

    rows_per_set = total_rows // num_sets
    sets = []
    for i in range(num_sets):
        vg_value = round(vg_start + i * vg_step, 6)
        chunk = df_extracted.iloc[i * rows_per_set:(i + 1) * rows_per_set].reset_index(drop=True)
        sets.append((vg_value, chunk))

    log(f"Split into {num_sets} set(s) by VG: {[_format_vg(vg) for vg, _ in sets]}")
    return sets


def process_file(raw_data_file, opju_file_path, target_columns=None, width_mm=None, log=print):
    """Read raw_data_file, extract the relevant columns, and save an Origin project to opju_file_path.

    Auto-detects whether the file is an Output (VD-ID family-of-curves) or Transfer
    characteristic from its SetupTitle. Output files always extract VD/ID and get
    split into one set per VG step, laid out side by side. Transfer (or unrecognized)
    files use target_columns as before.
    """

    if not target_columns:
        target_columns = DEFAULT_TARGET_COLUMNS

    # Set Origin to run invisibly
    op.set_show(False)

    log("Reading and cleaning raw measurement file...")

    rows = _read_rows(raw_data_file, log)
    if rows is None:
        return False

    measurement_type = _detect_measurement_type(rows)

    if measurement_type == 'output':
        log("Detected an Output (VD-ID) characteristic file.")
        sets = _extract_output_sets(rows, log, width_mm)
        if not sets:
            return False

        frames = []
        long_names = []
        units = []
        comments = []
        for i, (vg_value, chunk) in enumerate(sets, start=1):
            chunk = chunk.copy()
            chunk.columns = [f"S{i}_{col}" for col in OUTPUT_COLUMNS]
            frames.append(chunk)
            for col in OUTPUT_COLUMNS:
                desc, unit = PARAM_INFO.get(col, (col, ''))
                long_names.append(desc)
                units.append(unit)
                comments.append(f"VG={_format_vg(vg_value)}")

        df_extracted = pd.concat(frames, axis=1)
        sheet_name = "Output_Data"
        axis_designation = 'xy' * len(sets)
    else:
        df_extracted = _extract_dataframe(rows, target_columns, log, width_mm)
        if df_extracted is None:
            return False

        long_names = [PARAM_INFO.get(col, (col, ''))[0] for col in target_columns]
        units = [PARAM_INFO.get(col, (col, ''))[1] for col in target_columns]
        comments = None
        sheet_name = "Extracted_Data"
        axis_designation = 'x' + 'y' * (len(target_columns) - 1) if len(target_columns) > 1 else 'y'

    # --- Origin Export Section ---
    try:
        op.new()
        wks = op.new_sheet()
        wks.name = sheet_name

        log("Pushing extracted data to Origin...")
        wks.from_df(df_extracted)

        # 'L' = Long Name, 'U' = Units, 'C' = Comments (holds the source VG for Output sets)
        wks.set_labels(long_names, 'L')
        wks.set_labels(units, 'U')
        if comments:
            wks.set_labels(comments, 'C')

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


def process_folder(input_folder, opju_file_path, target_columns=None, width_mm=None, log=print):
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
            rows = _read_rows(raw_data_file, log)
            df_extracted = _extract_dataframe(rows, target_columns, log, width_mm) if rows is not None else None
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
    channel_width_mm = None  # required if ID/IG/dID/Imax/Imin/gm/gmmax are among the target columns

    if not process_file(raw_data_file, opju_file_path, width_mm=channel_width_mm):
        sys.exit(1)
