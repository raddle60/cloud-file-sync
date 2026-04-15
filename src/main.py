import argparse
import sys
import signal
import os
from config.config_loader import ConfigLoader
from core.crypto import derive_key, CryptoManager
from core.sync_engine import SyncEngine
from core.file_watcher import FileWatcher
from storage.sync_state import SyncState
from cloud.baidu_bos import BaiduBOS
from models.sync_pair import SyncPair, CloudType

_global_watcher = None

def parse_args(args=None):
    parser = argparse.ArgumentParser(description='Cloud File Sync Tool')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    start_parser = subparsers.add_parser('start', help='Start sync daemon')
    start_parser.add_argument('--config', required=True, help='Config file path')
    start_parser.add_argument('--daemon', action='store_true', help='Run as daemon')

    sync_parser = subparsers.add_parser('sync', help='Run one-time sync')
    sync_parser.add_argument('--config', required=True, help='Config file path')

    subparsers.add_parser('stop', help='Stop sync daemon')

    return parser.parse_args(args)

def create_cloud_storage(config):
    """根据 cloud_type 创建云端存储实例"""
    if not config.sync_pairs:
        raise ValueError("No sync_pairs configured")

    if config.cloud_type == CloudType.BAIDU_BOS:
        return BaiduBOS(
            access_key_id=os.environ.get('BOS_ACCESS_KEY_ID', ''),
            access_key_secret=os.environ.get('BOS_ACCESS_KEY_SECRET', ''),
            endpoint=os.environ.get('BOS_ENDPOINT', ''),
            bucket_name=config.sync_pairs[0].remote.split('/')[0]
        )
    else:
        raise ValueError(f"Unsupported cloud_type: {config.cloud_type}")

def start_sync(config_path: str, daemon: bool = False):
    global _global_watcher

    # 加载配置
    loader = ConfigLoader(config_path)
    config = loader.load()

    # 验证 remote 路径不冲突
    config.validate_remote_paths()

    # 创建加密管理器
    crypto = None
    if config.encryption_enabled:
        key = derive_key(config.encryption_key)
        crypto = CryptoManager(key)

    # 创建同步状态
    state = SyncState()

    # 为每个sync_pair创建SyncEngine
    engines = []
    for sync_pair_config in config.sync_pairs:
        sync_pair = SyncPair(
            local=sync_pair_config.local,
            remote=sync_pair_config.remote,
            encryption_enabled=config.encryption_enabled
        )

        cloud = create_cloud_storage(config)

        engine = SyncEngine(
            sync_pair=sync_pair,
            state=state,
            cloud_storage=cloud,
            crypto=crypto,
            config_key=config.encryption_key
        )
        engines.append(engine)

    def on_file_changed(files):
        for engine in engines:
            engine.full_sync()

    def on_periodic_check():
        for engine in engines:
            changes = engine.check_cloud_changes()
            for change in changes:
                if change['type'] == 'new':
                    engine.download_from_cloud(change['cloud_name'], change['meta'])
                elif change['type'] == 'modified':
                    # 比较本地和云端，决定是否下载
                    pass
                elif change['type'] == 'deleted':
                    # 删除本地文件
                    pass

    # 创建文件监听器
    _global_watcher = FileWatcher(
        watch_path=config.sync_pairs[0].local,
        debounce_seconds=10.0,
        callback=on_file_changed,
        periodic_callback=on_periodic_check,
        periodic_interval=60.0
    )

    # 执行初始全量同步
    for engine in engines:
        engine.full_sync()

    if not daemon:
        # 前台模式，阻塞监听
        print(f"Syncing started. Watching {config.sync_pairs[0].local}")
        signal.signal(signal.SIGINT, lambda s, f: stop_sync())
        signal.signal(signal.SIGTERM, lambda s, f: stop_sync())
        _global_watcher.start()
    else:
        # Daemon模式
        _global_watcher.start()
        print(f"Sync daemon started in background")

def stop_sync():
    global _global_watcher
    if _global_watcher:
        _global_watcher.stop()
        _global_watcher = None
    print("Sync stopped")

def run_sync_once(config_path: str):
    """执行一次同步"""
    loader = ConfigLoader(config_path)
    config = loader.load()

    crypto = None
    if config.encryption_enabled:
        key = derive_key(config.encryption_key)
        crypto = CryptoManager(key)

    state = SyncState()

    for sync_pair_config in config.sync_pairs:
        sync_pair = SyncPair(
            local=sync_pair_config.local,
            remote=sync_pair_config.remote,
            encryption_enabled=config.encryption_enabled
        )

        cloud = create_cloud_storage(config)

        engine = SyncEngine(
            sync_pair=sync_pair,
            state=state,
            cloud_storage=cloud,
            crypto=crypto,
            config_key=config.encryption_key
        )
        engine.full_sync()

    print("Sync completed")

def main():
    args = parse_args()

    if args.command == 'start':
        start_sync(args.config, args.daemon)
    elif args.command == 'sync':
        run_sync_once(args.config)
    elif args.command == 'stop':
        stop_sync()
    else:
        print("Unknown command")
        sys.exit(1)

if __name__ == '__main__':
    main()