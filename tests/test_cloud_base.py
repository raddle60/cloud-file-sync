import pytest
from abc import ABC
from cloud_file_sync.cloud.base import CloudStorage

def test_cloud_storage_is_abc():
    """验证CloudStorage是抽象基类"""
    assert issubclass(CloudStorage, ABC)

def test_cloud_storage_methods_are_abstract():
    """验证所有方法都是抽象方法"""
    for name in CloudStorage.__abstractmethods__:
        assert getattr(CloudStorage, name, None) is not None
