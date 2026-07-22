import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from dataHandler import ALL_PARAMETERS, DEFAULT_TARGET_COLUMNS, PER_WIDTH_PARAMS, process_file, process_folder


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV -> Origin Converter")
        self.geometry("880x600")
        self.resizable(True, True)

        self.mode = tk.StringVar(value="batch")
        self.input_label_var = tk.StringVar(value="Input folder:")
        self.output_label_var = tk.StringVar(value="Output .opju file (combined):")

        self.csv_path = tk.StringVar()
        self.opju_path = tk.StringVar()
        self.width_mm = tk.StringVar(value="0.1")
        self.param_vars = {
            name: tk.BooleanVar(value=name in DEFAULT_TARGET_COLUMNS)
            for name in ALL_PARAMETERS
        }

        pad = {"padx": 8, "pady": 6}

        # Mode selector
        mode_frame = tk.Frame(self)
        mode_frame.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 0))
        tk.Label(mode_frame, text="Mode:").pack(side="left")
        tk.Radiobutton(
            mode_frame, text="Single CSV file", variable=self.mode, value="single",
            command=self.update_mode,
        ).pack(side="left", padx=4)
        tk.Radiobutton(
            mode_frame, text="Folder of CSV files (batch)", variable=self.mode, value="batch",
            command=self.update_mode,
        ).pack(side="left", padx=4)

        # Input row
        tk.Label(self, textvariable=self.input_label_var).grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.csv_path, width=100).grid(row=1, column=1, sticky="ew", **pad)
        tk.Button(self, text="Browse...", command=self.browse_input).grid(row=1, column=2, **pad)

        # Output row
        tk.Label(self, textvariable=self.output_label_var).grid(row=2, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.opju_path, width=100).grid(row=2, column=1, sticky="ew", **pad)
        tk.Button(self, text="Browse...", command=self.browse_output).grid(row=2, column=2, **pad)

        # Parameter checkboxes
        param_frame = tk.LabelFrame(self, text="Parameters to extract")
        param_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=6)

        columns = 4
        for i, name in enumerate(ALL_PARAMETERS):
            r, c = divmod(i, columns)
            tk.Checkbutton(param_frame, text=name, variable=self.param_vars[name]).grid(
                row=r, column=c, sticky="w", padx=8, pady=2
            )

        select_frame = tk.Frame(self)
        select_frame.grid(row=4, column=0, columnspan=3)
        tk.Button(select_frame, text="Select All", command=self.select_all).pack(side="left", padx=4)
        tk.Button(select_frame, text="Clear All", command=self.clear_all).pack(side="left", padx=4)

        # Channel width (needed to normalize currents/transconductance by device width)
        tk.Label(self, text="Channel width (mm):").grid(row=5, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.width_mm, width=15).grid(row=5, column=1, sticky="w", **pad)
        tk.Label(
            self, text="Required for ID, IG, dID, Imax, Imin, gm, gmmax (-> mA/mm, mS/mm)",
            fg="gray",
        ).grid(row=5, column=2, sticky="w", padx=8)

        # Run button
        self.run_button = tk.Button(self, text="Run", command=self.run_clicked, width=15)
        self.run_button.grid(row=6, column=1, pady=12)

        # Log area
        self.log_widget = scrolledtext.ScrolledText(self, height=15, state="disabled")
        self.log_widget.grid(row=7, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)

        self.grid_rowconfigure(7, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def update_mode(self):
        self.csv_path.set("")
        self.opju_path.set("")
        if self.mode.get() == "single":
            self.input_label_var.set("Input CSV file:")
            self.output_label_var.set("Output .opju file:")
        else:
            self.input_label_var.set("Input folder:")
            self.output_label_var.set("Output .opju file (combined):")

    def select_all(self):
        for var in self.param_vars.values():
            var.set(True)

    def clear_all(self):
        for var in self.param_vars.values():
            var.set(False)

    def browse_input(self):
        if self.mode.get() == "single":
            path = filedialog.askopenfilename(
                title="Select input CSV file",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if path:
                self.csv_path.set(path)
                if not self.opju_path.get():
                    default_name = os.path.splitext(os.path.basename(path))[0] + ".opju"
                    self.opju_path.set(f"{os.path.dirname(path)}/{default_name}")
        else:
            path = filedialog.askdirectory(title="Select folder containing CSV files")
            if path:
                self.csv_path.set(path)
                if not self.opju_path.get():
                    default_name = os.path.basename(os.path.normpath(path)) + ".opju"
                    self.opju_path.set(f"{path}/{default_name}")

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Select output Origin project location",
            defaultextension=".opju",
            filetypes=[("Origin project", "*.opju"), ("All files", "*.*")],
        )
        if path:
            self.opju_path.set(path)

    def log(self, message):
        def append():
            self.log_widget.configure(state="normal")
            self.log_widget.insert(tk.END, str(message) + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.configure(state="disabled")

        self.after(0, append)

    def run_clicked(self):
        batch = self.mode.get() == "batch"
        input_path = self.csv_path.get().strip()
        output_path = self.opju_path.get().strip()

        if not input_path:
            messagebox.showerror("Missing input", f"Please choose an input {'folder' if batch else 'CSV file'}.")
            return
        if not output_path:
            messagebox.showerror("Missing output", "Please choose an output .opju location.")
            return

        if batch:
            if not os.path.isdir(input_path):
                messagebox.showerror("Invalid input", f"Folder not found:\n{input_path}")
                return
        else:
            if not os.path.isfile(input_path):
                messagebox.showerror("Invalid input", f"CSV file not found:\n{input_path}")
                return

        target_columns = [name for name in ALL_PARAMETERS if self.param_vars[name].get()]
        if not target_columns:
            messagebox.showerror("No parameters selected", "Please select at least one parameter to extract.")
            return

        # Parsed whenever present so it's available for auto-detected Output files too
        # (those always extract VD/ID regardless of which Transfer checkboxes are set).
        width_mm = None
        width_text = self.width_mm.get().strip()
        if width_text:
            try:
                width_mm = float(width_text)
                if width_mm <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid channel width", "Channel width must be a positive number.")
                return

        needs_width = any(col in PER_WIDTH_PARAMS for col in target_columns)
        if needs_width and width_mm is None:
            messagebox.showerror(
                "Missing channel width",
                "Please enter the channel width (mm) — it's required to convert "
                "ID/IG/dID/Imax/Imin/gm/gmmax to mA/mm or mS/mm.",
            )
            return

        self.run_button.configure(state="disabled")
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state="disabled")

        def worker():
            warning = None
            try:
                if batch:
                    success_count, failure_count, saved = process_folder(
                        input_path, output_path, target_columns=target_columns, width_mm=width_mm, log=self.log
                    )
                    success = saved
                    if success and failure_count > 0:
                        warning = f"{failure_count} file(s) were skipped. See log for details."
                else:
                    success = process_file(
                        input_path, output_path, target_columns=target_columns, width_mm=width_mm, log=self.log
                    )
            except Exception as e:
                self.log(f"Unexpected error: {e}")
                success = False

            def finish():
                self.run_button.configure(state="normal")
                if success:
                    messagebox.showinfo("Done", warning or "Conversion completed successfully!")
                else:
                    messagebox.showerror("Failed", "Conversion failed. See log for details.")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
