import pytest
import tempfile
import time
import threading
from unittest.mock import Mock, patch
from cloud_file_sync.core.file_watcher import FileWatcher

def test_file_watcher_init():
    watcher = FileWatcher("/tmp", debounce_seconds=10)
    assert watcher.watch_path == "/tmp"
    assert watcher.debounce_seconds == 10

def test_file_watcher_debounce_timer():
    """测试防抖计时器"""
    with patch('cloud_file_sync.core.file_watcher.Observer') as mock_observer:
        with tempfile.TemporaryDirectory() as tmpdir:
            callback = Mock()
            watcher = FileWatcher(tmpdir, debounce_seconds=1, callback=callback)

            # 触发事件
            watcher.on_file_changed("test.txt")
            assert not callback.called

            # 等待2秒（超过debounce时间）
            time.sleep(1.5)
            assert callback.called

            callback.reset_mock()

            # 快速连续触发两次
            watcher.on_file_changed("test.txt")
            watcher.on_file_changed("test.txt")
            time.sleep(1.5)
            # 应该只触发一次
            assert callback.call_count == 1

def test_file_watcher_start_stop():
    with patch('cloud_file_sync.core.file_watcher.Observer') as mock_observer:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_observer_instance = Mock()
            mock_observer.return_value = mock_observer_instance

            watcher = FileWatcher(tmpdir, debounce_seconds=10)

            watcher.start()
            mock_observer_instance.start.assert_called_once()

            watcher.stop()
            mock_observer_instance.stop.assert_called_once()