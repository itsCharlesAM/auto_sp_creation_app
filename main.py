import os
import pyodbc
import chardet
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    result = chardet.detect(raw_data)
    return result['encoding']


def execute_sql_batches(cursor, sql_script, log_callback):
    batches = re.split(r'(?im)^\s*GO\s*$', sql_script, flags=re.MULTILINE)
    for batch in batches:
        batch = batch.strip()
        if batch:
            try:
                cursor.execute(batch)
            except Exception as e:
                log_callback(
                    f"Error executing batch:\n{batch[:100]}...\nError: {e}")


class SPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Stored Procedure Creator")

        # SQL Connection Frame
        conn_frame = tk.LabelFrame(root, text="SQL Server Connection")
        conn_frame.pack(fill="x", padx=10, pady=5)

        self.server = self._add_labeled_entry(conn_frame, "Server:")
        self.database = self._add_labeled_entry(conn_frame, "Database:")
        self.username = self._add_labeled_entry(conn_frame, "Username:")

        # Password row with Show/Hide
        pwd_frame = tk.Frame(conn_frame)
        pwd_frame.pack(fill="x", padx=5, pady=2)
        tk.Label(pwd_frame, text="Password:", width=12).pack(side="left")

        self.password = tk.Entry(pwd_frame, show="*")
        self.password.pack(side="left", fill="x", expand=True)

        # Test Connection button
        test_btn = tk.Button(
            conn_frame, text="Test Connection", command=self.test_connection)
        test_btn.pack(pady=5)

        self.show_password = False
        toggle_btn = tk.Button(pwd_frame, text="Show", width=6,
                               command=self.toggle_password)
        toggle_btn.pack(side="left", padx=5)
        self.toggle_btn = toggle_btn  # store for later text change

        # Directory & SP List
        list_frame = tk.LabelFrame(root, text="SQL files")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        dir_btn = tk.Button(
            list_frame, text="Select SQL files", command=self.load_files)
        dir_btn.pack(pady=5)

        self.file_listbox = tk.Listbox(
            list_frame, selectmode=tk.MULTIPLE, width=100)
        self.file_listbox.pack(padx=5, pady=5, fill="both", expand=True)

        btn_frame = tk.Frame(list_frame)
        btn_frame.pack()

        tk.Button(btn_frame, text="Select All",
                  command=self.select_all).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Unselect All",
                  command=self.unselect_all).pack(side="left", padx=5)

        # Run Button
        tk.Button(root, text="Create Selected SPs",
                  command=self.create_stored_procedures, bg="green", fg="white").pack(pady=5)

        # Log output
        log_frame = tk.LabelFrame(root, text="Log Output")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=15)
        self.log_text.pack(fill="both", expand=True)

        self.sql_files_directory = ""

    def _add_labeled_entry(self, parent, label, show=None):
        frame = tk.Frame(parent)
        frame.pack(fill="x", padx=5, pady=2)
        tk.Label(frame, text=label, width=12).pack(side="left")
        entry = tk.Entry(frame, show=show) if show else tk.Entry(frame)
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def load_files(self):
        files = filedialog.askopenfilenames(
            title="Select SQL Files",
            filetypes=[("SQL Files", "*.sql")],
            initialdir=os.getcwd()
        )

        if files:
            self.sql_files_directory = os.path.dirname(
                files[0])  # Base folder for reference
            self.file_listbox.delete(0, tk.END)
            self.sql_files = []

            for file_path in files:
                filename = os.path.basename(file_path)
                self.file_listbox.insert(tk.END, filename)
                # Store full path for execution
                self.sql_files.append(file_path)

            self.log(
                f"Loaded {len(files)} SQL file(s) from: {self.sql_files_directory}")

    def select_all(self):
        self.file_listbox.select_set(0, tk.END)

    def unselect_all(self):
        self.file_listbox.select_clear(0, tk.END)

    def create_stored_procedures(self):
        server = self.server.get().strip()
        database = self.database.get().strip()
        username = self.username.get().strip()
        password = self.password.get().strip()

        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning(
                "No Selection", "Please select at least one SQL file.")
            return

        if not all([server, database, username, password]):
            messagebox.showwarning(
                "Missing Input", "Please fill in all connection fields.")
            return

        try:
            # Connect to the SQL Server
            connection = pyodbc.connect(
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};DATABASE={database};UID={username};PWD={password}"
            )
            cursor = connection.cursor()

            # Confirm connected database
            cursor.execute("SELECT DB_NAME() AS CurrentDatabase")
            row = cursor.fetchone()
            self.log(
                f"Connected to server: {server}, database: {row.CurrentDatabase}")

            # Get list of existing stored procedures
            cursor.execute("""
                SELECT s.name AS schema_name, p.name AS proc_name
                FROM sys.procedures p
                JOIN sys.schemas s ON p.schema_id = s.schema_id
            """)
            existing_sps = {
                f"{row.schema_name.lower()}.{row.proc_name.lower()}" for row in cursor.fetchall()}

            # Process only selected files
            for i in selected_indices:
                filename = self.file_listbox.get(i)
                file_path = os.path.join(self.sql_files_directory, filename)
                self.log(f"\nProcessing file: {filename}")

                # Detect file encoding
                encoding = detect_encoding(file_path)
                self.log(f"Detected encoding: {encoding}")

                # Read SQL file
                with open(file_path, "r", encoding=encoding) as sql_file:
                    sql_script = sql_file.read()

                # Remove any existing USE [DB] statements
                sql_script = re.sub(
                    r'(?i)^\s*USE\s+\[.*?\]\s*\n?', '', sql_script)

                # Extract procedure name
                match = re.search(
                    r'CREATE\s+PROCEDURE\s+(\[?\w+\]?\.?\[?\w+\]?)', sql_script, re.IGNORECASE)
                if not match:
                    self.log(
                        f"⚠️ Could not find a CREATE PROCEDURE statement in {filename}. Skipping.")
                    continue

                full_name = match.group(1).replace('[', '').replace(']', '')
                proc_name = full_name.lower()

                # If procedure exists, replace CREATE with ALTER
                if proc_name in existing_sps:
                    sql_script = re.sub(
                        r'(?i)\bCREATE\s+PROCEDURE\b', 'ALTER PROCEDURE', sql_script, count=1)
                    self.log(
                        f"🔁 Procedure '{proc_name}' exists. Using ALTER PROCEDURE.")
                else:
                    self.log(
                        f"🆕 Procedure '{proc_name}' does not exist. Using CREATE PROCEDURE.")

                # Add USE [database] at top
                sql_script = f"USE [{database}]\nGO\n{sql_script.strip()}"

                # Execute the SQL batches
                try:
                    try:
                        execute_sql_batches(cursor, sql_script, self.log)
                        connection.commit()
                        self.log(f"✅ {proc_name} executed successfully.\n")
                    except Exception as e:
                        self.log(f"❌ Error executing {proc_name}: {e}\n")
                except Exception as e:
                    self.log(f"❌ Error executing {filename}: {e}\n")

            cursor.close()
            connection.close()

            self.log("\nAll selected files processed successfully.\n")

        except Exception as ex:
            self.log(f"Failed to connect to the server: {ex}")

    def toggle_password(self):
        if self.show_password:
            self.password.config(show="*")
            self.toggle_btn.config(text="Show")
        else:
            self.password.config(show="")
            self.toggle_btn.config(text="Hide")
        self.show_password = not self.show_password

    def test_connection(self):
        server = self.server.get()
        database = self.database.get()
        username = self.username.get()
        password = self.password.get()

        if not all([server, database, username, password]):
            messagebox.showerror(
                "Missing Info", "Please fill in all connection fields.")
            return

        try:
            connection = pyodbc.connect(
                f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}",
                timeout=5
            )
            connection.close()
            messagebox.showinfo("Success", "Connection successful!")
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Failed to connect:\n{e}")


if __name__ == "__main__":

    root = tk.Tk()

    app = SPApp(root)

    root.mainloop()
