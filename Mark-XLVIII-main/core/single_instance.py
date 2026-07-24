"""Cross-process single-instance guard for the MARK desktop application."""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


class SingleInstanceGuard:
    def __init__(self, name: str = "jarvis-mark-xlviii") -> None:
        self.name = name
        self._handle: Any = None
        self._file: Any = None

    def acquire(self) -> bool:
        if self._handle is not None or self._file is not None:
            return True
        if os.name == "nt":
            return self._acquire_windows()
        return self._acquire_posix()

    def _acquire_windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        create_mutex.restype = wintypes.HANDLE
        handle = create_mutex(None, False, f"Local\\{self.name}")
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        self._handle = (kernel32, handle)
        return True

    def _acquire_posix(self) -> bool:
        import fcntl

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", self.name)
        path = Path(tempfile.gettempdir()) / f"{safe_name}.lock"
        lock_file = path.open("a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        self._file = lock_file
        return True

    def release(self) -> None:
        if self._handle is not None:
            kernel32, handle = self._handle
            kernel32.CloseHandle(handle)
            self._handle = None
        if self._file is not None:
            try:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            finally:
                self._file.close()
                self._file = None

    @staticmethod
    def focus_existing_window(
        title_fragment: str = "J.A.R.V.I.S",
        *,
        wait_seconds: float = 2.0,
    ) -> bool:
        """Restore and foreground the existing desktop window when available."""
        if os.name != "nt":
            return False

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window_enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        enum_windows = user32.EnumWindows
        enum_windows.argtypes = (window_enum_proc, wintypes.LPARAM)
        enum_windows.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.ShowWindowAsync.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindowAsync.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = (wintypes.HWND,)
        user32.BringWindowToTop.restype = wintypes.BOOL

        needle = title_fragment.casefold()
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            matches: list[int] = []

            @window_enum_proc
            def callback(hwnd: int, _lparam: int) -> bool:
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, len(buffer))
                if needle in buffer.value.casefold():
                    matches.append(hwnd)
                    return False
                return True

            enum_windows(callback, 0)
            if matches:
                hwnd = matches[0]
                user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def __enter__(self) -> "SingleInstanceGuard":
        if not self.acquire():
            raise RuntimeError("Another JARVIS MARK instance is already running.")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()
