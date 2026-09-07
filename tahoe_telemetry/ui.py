"""Tkinter/ttk user interface. Widget access is confined to the main thread."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .controller import TelemetryController, validate_clear_request
from .csvlog import CSVLogger
from .demo import DemoSource, HardwareSource
from .obd import PID_DEFINITIONS
from .settings import AppSettings, SettingsStore
from .transport import ELM327Transport, list_serial_ports


BG = "#10151c"
PANEL = "#18212b"
TEXT = "#f3f6f8"
MUTED = "#aebdca"
ACCENT = "#35b8ff"
GOOD = "#55d68b"
WARN = "#ffcc66"


class UILifecycle:
    """Coordinates UI workers without depending on Tk or blocking its thread."""

    def __init__(self, emit):
        self._emit = emit
        self._lock = threading.Lock()
        self._closing = False
        self._disconnecting = False
        self._connect_thread = None
        self._operation_thread = None

    def start_connect(self, source, connect) -> bool:
        with self._lock:
            if self._closing or (self._connect_thread and self._connect_thread.is_alive()):
                return False
            self._disconnecting = False

            def worker():
                try:
                    result = connect()
                    with self._lock:
                        accepted = not self._closing and not self._disconnecting
                    if accepted:
                        self._emit(("connected", result))
                    else:
                        source.close()
                except Exception as error:
                    source.close()
                    with self._lock:
                        accepted = not self._closing and not self._disconnecting
                    if accepted:
                        self._emit(("connect_error", str(error)))

            self._connect_thread = threading.Thread(target=worker, name="ELM-Connect", daemon=True)
            self._connect_thread.start()
            return True

    def start_operation(self, source, operation: str, success_event: str) -> bool:
        with self._lock:
            if self._closing or self._disconnecting or (self._operation_thread and self._operation_thread.is_alive()):
                return False

            def worker():
                try:
                    result = getattr(source, operation)()
                    with self._lock:
                        accepted = not self._closing and not self._disconnecting
                    if accepted:
                        self._emit((success_event, result))
                except Exception as error:
                    with self._lock:
                        accepted = not self._closing and not self._disconnecting
                    if accepted:
                        self._emit(("operation_error", str(error)))
                finally:
                    with self._lock:
                        self._operation_thread = None

            self._operation_thread = threading.Thread(target=worker, name=f"OBD-{operation}", daemon=True)
            self._operation_thread.start()
            return True

    def disconnect(self, controller) -> None:
        with self._lock:
            self._disconnecting = True
        if controller:
            controller.stop()

    def shutdown(self, controller) -> None:
        with self._lock:
            self._closing = True
            self._disconnecting = True
        if controller:
            controller.stop()

    @staticmethod
    def controller_event_is_terminal(event: str) -> bool:
        return event in {"error", "stopped"}


def format_value(value: object, unit: str, decimals: int) -> str:
    if value is None:
        return "Unsupported"
    if isinstance(value, (int, float)):
        rendered = f"{value:.{decimals}f}"
        return f"{rendered} {unit}" if unit else rendered
    return str(value)


def chart_points(values: list[float], width: int, height: int, padding: int = 10) -> list[tuple[float, float]]:
    if not values:
        return []
    low, high = min(values), max(values)
    usable_w, usable_h = width - padding * 2, height - padding * 2
    if len(values) == 1:
        xs = [width / 2]
    else:
        xs = [padding + index * usable_w / (len(values) - 1) for index in range(len(values))]
    if high == low:
        ys = [height / 2] * len(values)
    else:
        ys = [padding + (high - value) * usable_h / (high - low) for value in values]
    return list(zip(xs, ys))


class TahoeTelemetryApp:
    BAUDS = (9600, 38400, 57600, 115200)

    def __init__(self, root: tk.Tk, settings_store: SettingsStore | None = None):
        self.root = root
        self.store = settings_store or SettingsStore()
        self.settings = self.store.load()
        self.controller: TelemetryController | None = None
        self.source = None
        self._ui_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.value_vars: dict[str, tk.StringVar] = {}
        self.chart_canvases: dict[str, tk.Canvas] = {}
        self._closing = False
        self.lifecycle = UILifecycle(self._ui_events.put)
        self._configure_window()
        self._build_ui()
        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.root.after(50, self._drain_events)

    def _configure_window(self) -> None:
        self.root.title("Tahoe Telemetry — 2004 Chevrolet Tahoe 5.3L Flex-Fuel")
        self.root.geometry("1180x760")
        self.root.minsize(940, 640)
        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Value.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI Semibold", 15))
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", background=ACCENT, foreground="#081018")
        style.map("Accent.TButton", background=[("active", "#73ceff")])
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, rowheight=26)
        style.configure("Treeview.Heading", background="#243240", foreground=TEXT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8))

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="Tahoe Telemetry", font=("Segoe UI Semibold", 22)).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Generic OBD-II • engine/emissions data", style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        controls = ttk.Frame(header)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        header.columnconfigure(1, weight=1)
        self.port_var = tk.StringVar(value=self.settings.port)
        self.baud_var = tk.StringVar(value=str(self.settings.baudrate))
        self.protocol_choice = tk.StringVar(value=self.settings.protocol)
        self.demo_var = tk.BooleanVar(value=False)
        self.protocol_display = tk.StringVar(value="Disconnected")
        self.status_var = tk.StringVar(value="Ready — ignition ON before connecting")
        self.log_var = tk.StringVar(value="Logging off")

        ttk.Label(controls, text="COM port").grid(row=0, column=0, padx=3)
        self.port_box = ttk.Combobox(controls, textvariable=self.port_var, width=11, state="readonly")
        self.port_box.grid(row=1, column=0, padx=3)
        ttk.Button(controls, text="Refresh", command=self.refresh_ports).grid(row=1, column=1, padx=3)
        ttk.Label(controls, text="Baud").grid(row=0, column=2, padx=3)
        ttk.Combobox(controls, textvariable=self.baud_var, values=self.BAUDS, width=8, state="readonly").grid(row=1, column=2, padx=3)
        ttk.Label(controls, text="Protocol").grid(row=0, column=3, padx=3)
        ttk.Combobox(controls, textvariable=self.protocol_choice, values=("AUTO", "VPW"), width=8, state="readonly").grid(row=1, column=3, padx=3)
        ttk.Checkbutton(controls, text="Demo", variable=self.demo_var).grid(row=1, column=4, padx=6)
        self.connect_button = ttk.Button(controls, text="Connect", style="Accent.TButton", command=self.toggle_connection)
        self.connect_button.grid(row=1, column=5, padx=3)

        info = ttk.Frame(self.root, style="Panel.TFrame", padding=(12, 8))
        info.pack(fill="x", padx=12)
        ttk.Label(info, textvariable=self.status_var, style="Card.TLabel").pack(side="left")
        ttk.Label(info, textvariable=self.protocol_display, style="Card.TLabel").pack(side="right")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=10)
        self.dashboard = ttk.Frame(notebook, padding=8)
        self.charts = ttk.Frame(notebook, padding=8)
        self.diagnostics = ttk.Frame(notebook, padding=8)
        notebook.add(self.dashboard, text="Live data")
        notebook.add(self.charts, text="Rolling charts")
        notebook.add(self.diagnostics, text="Trouble codes")
        self._build_dashboard()
        self._build_charts()
        self._build_diagnostics()

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        footer.pack(fill="x")
        ttk.Label(footer, text="ABS, SRS and body modules are not guaranteed. PID availability is ECU-dependent.", style="Muted.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.log_var, style="Muted.TLabel").pack(side="right")

    def _build_dashboard(self) -> None:
        for column in range(4):
            self.dashboard.columnconfigure(column, weight=1, uniform="cards")
        for index, definition in enumerate(PID_DEFINITIONS.values()):
            row, column = divmod(index, 4)
            card = ttk.Frame(self.dashboard, style="Panel.TFrame", padding=12)
            card.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)
            var = tk.StringVar(value="Unsupported")
            self.value_vars[definition.key] = var
            ttk.Label(card, text=definition.label, style="Card.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=var, style="Value.TLabel").pack(anchor="w", pady=(4, 0))

    def _build_charts(self) -> None:
        numeric = [definition for definition in PID_DEFINITIONS.values() if definition.key != "fuel_type"]
        for column in range(3):
            self.charts.columnconfigure(column, weight=1, uniform="charts")
        for index, definition in enumerate(numeric):
            row, column = divmod(index, 3)
            frame = ttk.Frame(self.charts, style="Panel.TFrame", padding=5)
            frame.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            ttk.Label(frame, text=definition.label, style="Card.TLabel").pack(anchor="w")
            canvas = tk.Canvas(frame, height=72, bg=PANEL, highlightthickness=0, takefocus=1)
            canvas.pack(fill="both", expand=True)
            self.chart_canvases[definition.key] = canvas

    def _build_diagnostics(self) -> None:
        buttons = ttk.Frame(self.diagnostics)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Read stored / pending / permanent", command=self.read_dtcs).pack(side="left")
        ttk.Button(buttons, text="Clear codes…", command=self.clear_dtcs).pack(side="left", padx=6)
        ttk.Button(buttons, text="Start CSV log…", command=self.start_logging).pack(side="right")
        ttk.Button(buttons, text="Stop log", command=self.stop_logging).pack(side="right", padx=6)
        self.dtc_tree = ttk.Treeview(self.diagnostics, columns=("status", "code", "description"), show="headings")
        self.dtc_tree.heading("status", text="Status")
        self.dtc_tree.heading("code", text="Code")
        self.dtc_tree.heading("description", text="Description")
        self.dtc_tree.column("status", width=110, stretch=False)
        self.dtc_tree.column("code", width=90, stretch=False)
        self.dtc_tree.column("description", width=700)
        self.dtc_tree.pack(fill="both", expand=True)

    def refresh_ports(self) -> None:
        ports = list_serial_ports()
        values = [device for device, _ in ports]
        self.port_box["values"] = values
        if self.port_var.get() not in values:
            self.port_var.set(values[0] if values else "")
        if not values:
            self.status_var.set("No COM ports found — connect the adapter or use Demo mode")

    def toggle_connection(self) -> None:
        if self.controller:
            self.disconnect()
            return
        if not self.demo_var.get() and not self.port_var.get():
            messagebox.showerror("Connection error", "Select a COM port or enable Demo mode.")
            return
        self.connect_button.configure(state="disabled")
        self.status_var.set("Connecting…")
        source = DemoSource() if self.demo_var.get() else HardwareSource(ELM327Transport())
        self.source = source
        use_demo = self.demo_var.get()
        port = self.port_var.get()
        baudrate = int(self.baud_var.get())
        protocol = self.protocol_choice.get()

        connect = source.connect if use_demo else lambda: source.connect(port, baudrate, protocol)
        self.lifecycle.start_connect(source, connect)

    def _on_connected(self, detected: str) -> None:
        self.controller = TelemetryController(self.source, poll_interval=self.settings.poll_interval_ms / 1000)
        self.controller.start()
        self.protocol_display.set(f"Detected: {detected}")
        self.status_var.set("Connected; discovering supported Mode 01 PIDs…")
        self.connect_button.configure(text="Disconnect", state="normal")
        self._save_settings()

    def disconnect(self, status: str = "Disconnected") -> None:
        self.lifecycle.disconnect(self.controller)
        self.controller = None
        self.source = None
        self.connect_button.configure(text="Connect", state="normal")
        self.protocol_display.set("Disconnected")
        self.status_var.set(status)

    def _drain_events(self) -> None:
        while True:
            try:
                event, payload = self._ui_events.get_nowait()
            except queue.Empty:
                break
            if event == "connected":
                self._on_connected(str(payload))
            elif event == "connect_error":
                self.connect_button.configure(state="normal")
                self.status_var.set(str(payload))
                messagebox.showerror("Connection error", str(payload))
            elif event == "dtcs":
                self._show_dtcs(payload)
            elif event == "cleared":
                self.status_var.set("Mode 04 accepted; DTCs cleared and readiness monitors reset")
                self.read_dtcs()
            elif event == "operation_error":
                self.status_var.set(str(payload))
                messagebox.showerror("OBD-II error", str(payload))
        controller = self.controller
        if controller:
            while True:
                try:
                    event, payload = controller.events.get_nowait()
                except queue.Empty:
                    break
                if event == "sample":
                    controller.apply_sample(payload)
                    self._show_sample(payload)
                elif event == "supported":
                    self.status_var.set(f"Polling {len(payload)} supported Mode 01 PIDs")
                elif event in ("error", "warning"):
                    self.status_var.set(str(payload))
                    if event == "error":
                        self.disconnect(f"Disconnected: {payload}")
                elif event == "stopped" and self.controller is controller:
                    self.disconnect()
        if not self._closing:
            self.root.after(50, self._drain_events)

    def _show_sample(self, sample) -> None:
        for definition in PID_DEFINITIONS.values():
            value = sample.get(definition.key)
            self.value_vars[definition.key].set(format_value(value, definition.unit, definition.decimals))
        self._draw_charts()

    def _draw_charts(self) -> None:
        if not self.controller:
            return
        for key, canvas in self.chart_canvases.items():
            canvas.delete("all")
            width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 50)
            values = list(self.controller.history[key])
            points = chart_points(values, width, height)
            if len(points) > 1:
                canvas.create_line(*[coordinate for point in points for coordinate in point], fill=ACCENT, width=2, smooth=True)
            elif points:
                canvas.create_oval(points[0][0] - 2, points[0][1] - 2, points[0][0] + 2, points[0][1] + 2, fill=ACCENT, outline="")
            if not points:
                canvas.create_text(8, height / 2, anchor="w", text="Unsupported / waiting", fill=MUTED)

    def _run_source_operation(self, operation: str, success_event: str) -> None:
        if not self.source:
            messagebox.showinfo("Not connected", "Connect to an adapter or Demo mode first.")
            return

        if not self.lifecycle.start_operation(self.source, operation, success_event):
            self.status_var.set("Diagnostic operation already in progress or disconnecting")

    def read_dtcs(self) -> None:
        self._run_source_operation("read_dtcs", "dtcs")

    def _show_dtcs(self, groups) -> None:
        self.dtc_tree.delete(*self.dtc_tree.get_children())
        for status, records in groups.items():
            if records is None:
                self.dtc_tree.insert("", "end", values=(status, "—", "Unavailable / unsupported by ECU"))
                continue
            if not records:
                self.dtc_tree.insert("", "end", values=(status, "—", "No codes reported"))
            for record in records:
                self.dtc_tree.insert("", "end", values=(status, record.code, record.description))
        self.status_var.set("Diagnostic trouble code scan complete")

    def clear_dtcs(self) -> None:
        if not self.source:
            messagebox.showinfo("Not connected", "Connect to an adapter or Demo mode first.")
            return
        typed = simpledialog.askstring("Clear DTCs", "Type CLEAR exactly to continue:", parent=self.root)
        try:
            validate_clear_request(typed or "", True)
        except ValueError as error:
            if typed is not None:
                messagebox.showwarning("Clear blocked", str(error))
            return
        confirmed = messagebox.askyesno(
            "Final warning",
            "Mode 04 will erase diagnostic information and reset emissions readiness monitors. "
            "The vehicle may need a complete drive cycle before inspection readiness returns. Continue?",
            icon="warning",
        )
        try:
            validate_clear_request(typed, confirmed)
        except ValueError:
            self.status_var.set("Clearing cancelled; no command was sent.")
            return
        self._run_source_operation("clear_dtcs", "cleared")

    def start_logging(self) -> None:
        if not self.controller:
            messagebox.showinfo("Not connected", "Connect before starting a CSV log.")
            return
        initial = self.settings.log_directory or str(Path.cwd())
        directory = filedialog.askdirectory(title="Choose CSV log folder", initialdir=initial)
        if not directory:
            return
        logger = CSVLogger(Path(directory), [definition.key for definition in PID_DEFINITIONS.values()])
        self.controller.set_logger(logger)
        self.log_var.set(f"Logging: {logger.path.name}")
        self.settings = AppSettings(
            self.port_var.get(), int(self.baud_var.get()), self.protocol_choice.get(),
            self.settings.poll_interval_ms, directory,
        )
        self._save_settings()

    def stop_logging(self) -> None:
        if self.controller:
            self.controller.stop_logging()
        self.log_var.set("Logging off")

    def _save_settings(self) -> None:
        self.settings = AppSettings(
            self.port_var.get(), int(self.baud_var.get()), self.protocol_choice.get(),
            self.settings.poll_interval_ms, self.settings.log_directory,
        )
        try:
            self.store.save(self.settings)
        except OSError as error:
            self.status_var.set(f"Settings could not be saved: {error}")

    def shutdown(self) -> None:
        self._closing = True
        self.lifecycle.shutdown(self.controller)
        self._save_settings()
        self.root.destroy()
