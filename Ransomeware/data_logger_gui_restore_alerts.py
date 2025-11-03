import argparse
import os
import shutil
import time
import csv
import queue
from datetime import datetime, timezone
from collections import deque
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ---------- args ----------
parser = argparse.ArgumentParser(description="GUI file monitor with spike alerts")
parser.add_argument("--dir", "-d", default=r"D:\\MYPROJECTS\\IS\\testing", help="Directory to monitor")
parser.add_argument("--files", "-F", default="", help="Comma-separated files to filter (basenames or relpaths)")
parser.add_argument("--snapshot-dir", default="snapshots", help="Where initial snapshots are stored")
parser.add_argument("--duplicates-dir", default="duplicates", help="Where duplicates are stored when restoring")
parser.add_argument("--log", default="activity_restore_log.csv", help="CSV log file")
parser.add_argument("--spike-window", type=float, default=5.0, help="Seconds window to detect modification spike")
parser.add_argument("--spike-threshold", type=int, default=8, help="Number of modified files in window to trigger alert")
parser.add_argument("--alert-cooldown", type=float, default=60.0, help="Seconds to wait before re-alerting after a spike")
args = parser.parse_args()

TARGET_DIRECTORY = os.path.abspath(args.dir)

# parse files
if args.files and args.files.strip():
    raw = [s.strip() for s in args.files.split(",") if s.strip()]
    BASENAMES = set()
    RELPATHS = set()
    for token in raw:
        t = token.replace("\\", "/")
        if "/" in t:
            RELPATHS.add(os.path.normcase(os.path.normpath(t)))
        else:
            BASENAMES.add(t.lower())
else:
    BASENAMES = None
    RELPATHS = None

SNAPSHOT_DIR = os.path.abspath(args.snapshot_dir)
DUPLICATES_DIR = os.path.abspath(args.duplicates_dir)
LOG_FILE = os.path.abspath(args.log)

SPIKE_WINDOW_SEC = float(args.spike_window)
SPIKE_THRESHOLD = int(args.spike_threshold)
ALERT_COOLDOWN_SEC = float(args.alert_cooldown)

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(DUPLICATES_DIR, exist_ok=True)

CSV_FIELDS = ["timestamp_iso", "event_type", "event_path", "action_taken", "note"]

def csv_log(row):
    need_header = not os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if need_header:
            writer.writeheader()
        writer.writerow(row)

# ---------- snapshot helpers ----------
def create_initial_snapshot(target_dir):
    print("Creating initial snapshot...")
    if not os.path.isdir(target_dir):
        raise SystemExit(f"Directory does not exist: {target_dir}")
    for root, _, files in os.walk(target_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), target_dir)
            rel_norm = os.path.normcase(os.path.normpath(rel))
            take = False
            if BASENAMES is None and RELPATHS is None:
                take = True
            else:
                if BASENAMES and fname.lower() in BASENAMES:
                    take = True
                if RELPATHS and rel_norm in RELPATHS:
                    take = True
            if not take:
                continue
            src = os.path.join(root, fname)
            dst = os.path.join(SNAPSHOT_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.copy2(src, dst)
            except Exception as e:
                print(f"Warning: could not snapshot {src}: {e}")
    print("Initial snapshot complete.")

def snapshot_path_for(abs_path):
    try:
        rel = os.path.relpath(abs_path, TARGET_DIRECTORY)
    except Exception:
        return ""
    return os.path.join(SNAPSHOT_DIR, rel)

def update_snapshot_for(abs_path):
    sp = snapshot_path_for(abs_path)
    if not sp:
        return False, "no_snapshot_path"
    try:
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        shutil.copy2(abs_path, sp)
        return True, sp
    except Exception as e:
        return False, str(e)

def _is_monitored_path(abs_path):
    if BASENAMES is None and RELPATHS is None:
        return True
    try:
        rel = os.path.relpath(abs_path, TARGET_DIRECTORY)
    except Exception:
        rel = os.path.basename(abs_path)
    rel_norm = os.path.normcase(os.path.normpath(rel))
    if RELPATHS and rel_norm in RELPATHS:
        return True
    if BASENAMES and os.path.basename(abs_path).lower() in BASENAMES:
        return True
    return False

# ---------- watchdog handler ----------
class GuiEventHandler(FileSystemEventHandler):
    def __init__(self, q):
        super().__init__()
        self.q = q
    def _enqueue(self, ev_type, src_path, dest_path=None):
        check_path = src_path if src_path else (dest_path or "")
        if not check_path:
            return
        if not _is_monitored_path(os.path.abspath(check_path)):
            return
        item = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": ev_type,
            "src_path": os.path.abspath(src_path) if src_path else "",
            "dest_path": os.path.abspath(dest_path) if dest_path else ""
        }
        self.q.put(item)
    def on_created(self, event): self._enqueue("created", event.src_path)
    def on_deleted(self, event): self._enqueue("deleted", event.src_path)
    def on_modified(self, event):
        if event.is_directory:
            return
        self._enqueue("modified", event.src_path)
    def on_moved(self, event): self._enqueue("moved", event.src_path, event.dest_path)

# ---------- GUI ----------
class MonitorGUI:
    def __init__(self, root, event_q):
        self.root = root
        self.q = event_q
        self.root.title("Directory Monitor — Restore/Ignore (with Spike Alerts)")
        self.root.geometry("1000x580")

        # spike detection
        self.mod_deque = deque()
        self.last_alert_ts = 0

        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)
        filter_text = "(all files)" if (BASENAMES is None and RELPATHS is None) else "(filtered)"
        ttk.Label(top, text=f"Monitoring: {TARGET_DIRECTORY} {filter_text}").pack(side="left")
        ttk.Button(top, text="Refresh snapshot", command=self.refresh_snapshot).pack(side="right", padx=6)
        ttk.Button(top, text="Exit", command=self.on_exit).pack(side="right")

        mid = ttk.Panedwindow(root, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=8, pady=6)

        left_frame = ttk.Frame(mid, width=360)
        mid.add(left_frame, weight=1)
        ttk.Label(left_frame, text="Detected events (newest at top):").pack(anchor="w")
        self.listbox = tk.Listbox(left_frame, height=30)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        right_frame = ttk.Frame(mid)
        mid.add(right_frame, weight=3)
        ttk.Label(right_frame, text="Event details:").pack(anchor="w")
        self.detail = scrolledtext.ScrolledText(right_frame, height=14)
        self.detail.pack(fill="both", expand=False)

        btnframe = ttk.Frame(right_frame)
        btnframe.pack(fill="x", pady=8)
        self.ignore_btn = ttk.Button(btnframe, text="I'm me (ignore)", command=self.mark_ignore)
        self.ignore_btn.pack(side="left", padx=6)
        self.restore_btn = ttk.Button(btnframe, text="Not me — restore original & duplicate", command=self.restore_original)
        self.restore_btn.pack(side="left", padx=6)

        ttk.Label(right_frame, text="Action / status log:").pack(anchor="w")
        self.status = scrolledtext.ScrolledText(right_frame, height=12)
        self.status.pack(fill="both", expand=True)

        self.events = []
        self.selected_index = None

        self.root.after(200, self.poll_queue)

    def log_status(self, text):
        ts = datetime.now(timezone.utc).isoformat()
        self.status.insert("end", f"[{ts}] {text}\n")
        self.status.see("end")

    # spike helpers
    def _record_mod_event(self, abs_path):
        t = time.time()
        self.mod_deque.append((t, abs_path))
        cutoff = t - SPIKE_WINDOW_SEC
        while self.mod_deque and self.mod_deque[0][0] < cutoff:
            self.mod_deque.popleft()

    def _count_mods(self):
        cutoff = time.time() - SPIKE_WINDOW_SEC
        return sum(1 for t, _ in self.mod_deque if t >= cutoff)

    def _collect_recent_paths(self):
        cutoff = time.time() - SPIKE_WINDOW_SEC
        return [p for t, p in self.mod_deque if t >= cutoff]

    def _maybe_trigger_spike(self):
        count = self._count_mods()
        now_ts = time.time()
        if count >= SPIKE_THRESHOLD and (now_ts - self.last_alert_ts) > ALERT_COOLDOWN_SEC:
            self.last_alert_ts = now_ts
            recent_paths = list(dict.fromkeys(self._collect_recent_paths()))
            self.root.after(100, lambda: self._show_spike_alert(recent_paths))

    def _show_spike_alert(self, recent_paths):
        sample = recent_paths[:10]
        lines = ["Possible mass file modification detected:", ""]
        lines += [f"  {os.path.relpath(p, TARGET_DIRECTORY)}" for p in sample]
        if len(recent_paths) > len(sample):
            lines.append(f"  ... and {len(recent_paths)-len(sample)} more")
        lines.append("")
        lines.append("Is this you? (Yes = I'm making these changes)")
        summary = "\n".join(lines)

        try:
            status_text = self.status.get("1.0", "end").strip()
        except Exception:
            status_text = "(no status log available)"

        popup = tk.Toplevel(self.root)
        popup.title("Warning — possible ransomware activity")
        popup.geometry("720x420")
        popup.transient(self.root)
        popup.grab_set()

        lbl = ttk.Label(popup, text="Alert summary (recent files):", font=("TkDefaultFont", 10, "bold"))
        lbl.pack(anchor="w", padx=8, pady=(8, 0))

        summ_txt = tk.Text(popup, height=6, wrap="word")
        summ_txt.insert("1.0", summary)
        summ_txt.config(state="disabled")
        summ_txt.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        lbl2 = ttk.Label(popup, text="Action / status log:", font=("TkDefaultFont", 10, "bold"))
        lbl2.pack(anchor="w", padx=8)

        status_frame = ttk.Frame(popup)
        status_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        st = scrolledtext.ScrolledText(status_frame, wrap="word")
        st.insert("1.0", status_text)
        st.config(state="disabled")
        st.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", pady=(0, 10))
        answered = {"val": None}

        def on_yes():
            answered["val"] = True
            popup.destroy()

        def on_no():
            answered["val"] = False
            popup.destroy()

        yes_btn = ttk.Button(btn_frame, text="Yes — I'm making these changes", command=on_yes)
        yes_btn.pack(side="left", padx=12, ipadx=6)
        no_btn = ttk.Button(btn_frame, text="No — Someone else", command=on_no)
        no_btn.pack(side="left", padx=12, ipadx=6)

        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            popup.geometry(f"+{x + max(20, w//6)}+{y + 40}")
        except Exception:
            pass

        popup.wait_window()

        if answered["val"] is True:
            updated = 0
            for p in recent_paths:
                if os.path.isfile(p):
                    ok, info = update_snapshot_for(p)
                    if ok:
                        updated += 1
                        csv_log({"timestamp_iso": datetime.now(timezone.utc).isoformat(),
                                 "event_type": "snapshot_updated_by_user", "event_path": p,
                                 "action_taken": "snapshot_updated", "note": info})
            self.log_status(f"User confirmed activity (updated snapshots for {updated} files). Continuing monitoring.")
            return

        # Not me: bring GUI front and preselect matching event
        self.log_status("User indicated activity not by them. Please inspect and restore if needed.")
        csv_log({"timestamp_iso": datetime.now(timezone.utc).isoformat(),
                 "event_type": "user_reported_not_me", "event_path": ";".join(recent_paths),
                 "action_taken": "alert_shown", "note": f"count={len(recent_paths)}"})

        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

        idx_to_select = None
        for idx, ev in enumerate(self.events):
            if ev['src_path'] in recent_paths or ev['dest_path'] in recent_paths:
                idx_to_select = idx
                break

        if idx_to_select is not None:
            self.listbox.selection_clear(0, 'end')
            self.listbox.select_set(idx_to_select)
            self.listbox.activate(idx_to_select)
            try:
                self.listbox.see(idx_to_select)
            except Exception:
                pass
            self.on_select(None)
            messagebox.showinfo("Inspect & Restore", "Recent suspicious events have been selected. Click 'Not me — restore original & duplicate' to restore the selected file or inspect details.")
        else:
            messagebox.showinfo("Inspect", "Suspicious activity detected but matching event not found in the list. Check the Action / status log or click 'Refresh snapshot'.")

    # poll
    def poll_queue(self):
        changed = False
        while True:
            try:
                ev = self.q.get_nowait()
            except queue.Empty:
                break
            self.events.insert(0, ev)
            display_name = os.path.basename(ev['src_path']) or os.path.basename(ev['dest_path'])
            display_text = f"{ev['time']} — {ev['type']} — {display_name}"
            self.listbox.insert(0, display_text)
            changed = True

            if ev['type'] in ("modified", "created", "moved"):
                track_path = ev['src_path'] if ev['src_path'] else ev['dest_path']
                if track_path:
                    self._record_mod_event(track_path)

        if changed:
            self.log_status("New event(s) received.")
            self._maybe_trigger_spike()

        self.root.after(200, self.poll_queue)

    def on_select(self, evt):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        ev = self.events[idx]
        self.selected_index = idx
        lines = [
            f"Time (UTC): {ev['time']}",
            f"Event type: {ev['type']}",
            f"Source path: {ev['src_path']}",
            f"Dest path: {ev['dest_path']}",
            "",
            "Snapshot path (if exists):",
            snapshot_path_for(ev['src_path']) or "(none)"
        ]
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.see("1.0")

    def mark_ignore(self):
        if self.selected_index is None:
            messagebox.showinfo("Select event", "Please select an event to mark as 'I'm me'.")
            return
        ev = self.events[self.selected_index]
        self.log_status(f"Marked ignored: {ev['type']} on {ev['src_path']}")
        csv_log({
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "event_type": ev['type'],
            "event_path": ev['src_path'],
            "action_taken": "ignored_by_user",
            "note": "user indicated they performed the action"
        })
        # update snapshot
        if ev['src_path'] and os.path.isfile(ev['src_path']):
            ok, info = update_snapshot_for(ev['src_path'])
            if ok:
                self.log_status(f"Snapshot updated for {ev['src_path']}")
            else:
                self.log_status(f"Snapshot update failed for {ev['src_path']}: {info}")

    def restore_original(self):
        if self.selected_index is None:
            messagebox.showinfo("Select event", "Please select an event to restore.")
            return
        ev = self.events[self.selected_index]
        src_path = ev['src_path']
        if not src_path:
            messagebox.showwarning("No source path", "Event has no source path; cannot restore.")
            return
        snapshot_path = snapshot_path_for(src_path)
        if not snapshot_path or not os.path.isfile(snapshot_path):
            self.log_status(f"NO SNAPSHOT found for {src_path}. Cannot restore.")
            csv_log({
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "event_type": ev['type'],
                "event_path": src_path,
                "action_taken": "restore_failed_no_snapshot",
                "note": snapshot_path
            })
            messagebox.showerror("Snapshot missing", f"No snapshot found for:\n{src_path}\n\nPath expected:\n{snapshot_path}")
            return

        try:
            os.makedirs(os.path.dirname(src_path), exist_ok=True)
        except Exception as e:
            self.log_status(f"Could not ensure destination dir: {e}")
            messagebox.showerror("Error", f"Could not create destination directories for {src_path}:\n{e}")
            return

        try:
            shutil.copy2(snapshot_path, src_path)
        except Exception as e:
            self.log_status(f"Restore failed: {e}")
            csv_log({
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "event_type": ev['type'],
                "event_path": src_path,
                "action_taken": "restore_failed_copy_error",
                "note": str(e)
            })
            messagebox.showerror("Restore failed", f"Could not copy snapshot to:\n{src_path}\n\nError: {e}")
            return

        base = os.path.basename(src_path)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dup_name = f"{base}.{ts}.orig"
        rel = os.path.relpath(src_path, TARGET_DIRECTORY)
        dup_subdir = os.path.join(DUPLICATES_DIR, os.path.dirname(rel))
        os.makedirs(dup_subdir, exist_ok=True)
        dup_path = os.path.join(dup_subdir, dup_name)
        try:
            shutil.copy2(snapshot_path, dup_path)
        except Exception as e:
            self.log_status(f"Duplicate save failed: {e}")
            csv_log({
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "event_type": ev['type'],
                "event_path": src_path,
                "action_taken": "restore_but_duplicate_failed",
                "note": str(e)
            })
            messagebox.showwarning("Partial success", f"Restored {src_path} but failed to save duplicate:\n{e}")
            return

        self.log_status(f"Restored original for {src_path} and saved duplicate to {dup_path}")
        csv_log({
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "event_type": ev['type'],
            "event_path": src_path,
            "action_taken": "restored_and_duplicated",
            "note": dup_path
        })
        messagebox.showinfo("Restored", f"Restored original to:\n{src_path}\nDuplicate saved:\n{dup_path}")

    def refresh_snapshot(self):
        if messagebox.askyesno("Refresh snapshot", "Refreshing snapshots will overwrite stored snapshots from startup. Continue?"):
            try:
                if os.path.exists(SNAPSHOT_DIR):
                    shutil.rmtree(SNAPSHOT_DIR)
                os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                create_initial_snapshot(TARGET_DIRECTORY)
                self.log_status("Snapshot refreshed.")
            except Exception as e:
                self.log_status(f"Snapshot refresh failed: {e}")
                messagebox.showerror("Error", f"Snapshot refresh failed: {e}")

    def on_exit(self):
        if messagebox.askokcancel("Quit", "Stop monitoring and quit?"):
            self.root.quit()

# ---------- main ----------
def main():
    if not os.path.isdir(TARGET_DIRECTORY):
        raise SystemExit(f"Target directory not found: {TARGET_DIRECTORY}")

    create_initial_snapshot(TARGET_DIRECTORY)

    ev_q = queue.Queue()
    event_handler = GuiEventHandler(ev_q)
    observer = Observer()
    observer.schedule(event_handler, TARGET_DIRECTORY, recursive=True)
    observer.daemon = True
    observer.start()

    root = tk.Tk()
    gui = MonitorGUI(root, ev_q)

    try:
        root.mainloop()
    finally:
        observer.stop()
        observer.join(timeout=2)
        print("Stopped observer. Exiting.")

if __name__ == "__main__":
    main()
