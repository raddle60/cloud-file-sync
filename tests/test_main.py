import pytest
from unittest.mock import patch, Mock, MagicMock
import sys

# Mock the baidu module before importing main
sys.modules['baidu'] = MagicMock()
sys.modules['baidu.bce'] = MagicMock()
sys.modules['baidu.bce.bos'] = MagicMock()
sys.modules['baidu.bce.auth'] = MagicMock()

from cloud_file_sync.main import parse_args

def test_parse_args_start():
    args = parse_args(['start', '--config', 'config.json'])
    assert args.command == 'start'
    assert args.config == 'config.json'

def test_parse_args_sync():
    args = parse_args(['sync', '--config', 'config.json'])
    assert args.command == 'sync'

def test_parse_args_stop():
    args = parse_args(['stop'])
    assert args.command == 'stop'

def test_parse_args_with_daemon():
    args = parse_args(['start', '--config', 'config.json', '--daemon'])
    assert args.daemon == True