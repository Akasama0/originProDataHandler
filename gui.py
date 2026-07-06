import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from dataHandler import process_file


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV -> Origin Converter")
        self.geometry("640x420")
        self.resizable(True, True)

        self.csv_path = tk.StringVar()
        self.opju_path = tk.StringVar()

        pad = {"padx": 8, "pady": 6}

        # CSV input row
        tk.Label(self, text="Input CSV file:").grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.csv_path, width=60).grid(row=0, column=1, **pad)
        tk.Button(self, text="Browse...", command=self.browse_csv).grid(row=0, column=2, **pad)

        # Output opju row
        tk.Label(self, text="Output .opju file:").grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(self, textvariable=self.opju_path, width=60).grid(row=1, column=1, **pad)
        tk.Button(self, text="Browse...", command=self.browse_opju).grid(row=1, column=2, **pad)

        # Run button
        self.run_button = tk.Button(self, text="Run", command=self.run_clicked, width=15)
        self.run_button.grid(row=2, column=1, pady=12)

        # Log area
        self.log_widget = scrolledtext.ScrolledText(self, height=15, state="disabled")
        self.log_widget.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select input CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.csv_path.set(path)
            if not self.opju_path.get():
                default_name = os.path.splitext(os.path.basename(path))[0] + ".opju"
                self.opju_path.set(os.path.join(os.path.dirname(path), default_name))

    def browse_opju(self):
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
        csv_path = self.csv_path.get().strip()
        opju_path = self.opju_path.get().strip()

        if not csv_path:
            messagebox.showerror("Missing input", "Please choose an input CSV file.")
            return
        if not opju_path:
            messagebox.showerror("Missing output", "Please choose an output .opju location.")
            return
        if not os.path.isfile(csv_path):
            messagebox.showerror("Invalid input", f"CSV file not found:\n{csv_path}")
            return

        self.run_button.configure(state="disabled")
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state="disabled")

        def worker():
            try:
                success = process_file(csv_path, opju_path, log=self.log)
            except Exception as e:
                self.log(f"Unexpected error: {e}")
                success = False

            def finish():
                self.run_button.configure(state="normal")
                if success:
                    messagebox.showinfo("Done", "Conversion completed successfully!")
                else:
                    messagebox.showerror("Failed", "Conversion failed. See log for details.")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
