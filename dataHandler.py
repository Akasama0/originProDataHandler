import originpro as op
import pandas as pd
import csv
import sys


def process_file(raw_data_file, opju_file_path, log=print):
    """Read raw_data_file, extract VG/ID columns, and save an Origin project to opju_file_path."""

    # Set Origin to run invisibly
    op.set_show(False)

    log("Reading and cleaning raw measurement file...")

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
        return False

    if not filtered_rows:
        log("Error: Could not find any 'DataName' or 'DataValue' rows in the file.")
        return False

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

        # 7. Extract the specific columns you care about
        # IMPORTANT: If the log statement above shows 'Vg' instead of 'VG', change it here!
        target_columns = ['VG', 'ID']

        # Double-check that our targets actually exist before extracting
        missing_cols = [col for col in target_columns if col not in df_data.columns]
        if missing_cols:
            log(f"--> ERROR: Still missing these columns: {missing_cols}")
            log("--> Please update the 'target_columns' list in the script to match the printed available columns.")
            return False

        df_extracted = df_data[target_columns].dropna()

    except KeyError as e:
        log(f"Error: Could not find columns 'VG' or 'ID'. Check the exact spelling in your DataName row. {e}")
        return False
    except Exception as e:
        log(f"Failed to clean data: {e}")
        return False

    # --- Origin Export Section ---
    try:
        op.new()
        wks = op.new_sheet()
        wks.name = "VG_ID_Data"

        log("Pushing extracted data to Origin...")
        wks.from_df(df_extracted)

        # 10. Configure Origin Columns correctly using originpro methods
        # 'L' stands for Long Name, 'U' stands for Units
        wks.set_labels(['Gate Voltage', 'Drain Current'], 'L')
        wks.set_labels(['V', 'A'], 'U')

        # Set the column designations (First column to X, Second column to Y)
        wks.cols_axis('xy')

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


if __name__ == "__main__":
    # Define file paths (Use raw strings 'r' to handle Windows backslashes)
    raw_data_file = r"C:\Users\Akasa\保存\研究\kanta_cv\60s30s\半パラ\20260706mobility\Transfer VDS=0.1V [60s30s1151(3) ; 2026_07_06 9_02_48].csv"
    opju_file_path = r"C:\Users\Akasa\保存\研究\kanta_cv\60s30s\20260706transfer.opju"

    if not process_file(raw_data_file, opju_file_path):
        sys.exit(1)
