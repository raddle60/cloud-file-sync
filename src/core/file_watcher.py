import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

class DebouncedFileHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_seconds: float = 10.0):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._timer: threading.Timer = None
        self._changed_files = set()
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._notify_change(event.src_path)

    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._notify_change(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._notify_change(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._notify_change(event.dest_path)

    def _notify_change(self, file_path: str):
        with self._lock:
            self._changed_files.add(file_path)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._trigger_sync)
            self._timer.start()

    def _trigger_sync(self):
        with self._lock:
            files = list(self._changed_files)
            self._changed_files.clear()
        if files and self.callback:
            self.callback(files)

class PeriodicChecker:
    """周期性任务检查器"""
    def __init__(self, interval_seconds: float, callback):
        self.interval = interval_seconds
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(self.interval)
            if not self._stop_event.is_set():
                self.callback()

class FileWatcher:
    def __init__(self, watch_path: str, debounce_seconds: float = 10.0,
                 callback=None, periodic_callback=None, periodic_interval: float = 60.0):
        self.watch_path = watch_path
        self.debounce_seconds = debounce_seconds
        self.callback = callback
        self.periodic_callback = periodic_callback
        self.periodic_interval = periodic_interval
        self._observer = Observer()
        self._handler = DebouncedFileHandler(callback, debounce_seconds)
        self.periodic_checker = None
        if periodic_callback:
            self.periodic_checker = PeriodicChecker(periodic_interval, periodic_callback)

    def start(self):
        self._observer.schedule(self._handler, self.watch_path, recursive=True)
        self._observer.start()
        if self.periodic_checker:
            self.periodic_checker.start()

    def stop(self):
        if self.periodic_checker:
            self.periodic_checker.stop()
        self._observer.stop()
        self._observer.join()

    def on_file_changed(self, file_path: str):
        """手动触发文件变化事件"""
        self._handler._notify_change(file_path)