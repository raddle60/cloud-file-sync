# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cloud-file-sync is a bidirectional sync tool between local directories and cloud storage (Baidu BOS). It supports encrypted and non-encrypted modes with atomic operations.

## Common Commands

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_sync_engine.py

# Run specific test
pytest tests/test_sync_engine.py::test_cloud_name_generation_encrypted -v
```

## Architecture

### Core Flow

1. `main.py` loads config → creates one `SyncEngine` per `sync_pair`
2. `SyncEngine.full_sync()` scans local files and syncs with cloud
3. `FileWatcher` monitors local changes (10s debounce) and checks cloud periodically (60s)
4. `CloudStorage` abstract interface allows pluggable backends (Baidu BOS built-in)

### Key Components

- **SyncEngine** (`core/sync_engine.py`): Core sync logic - handles cloud name generation, atomic upload/download, cloud change detection via `_last_cloud_metas`
- **FileWatcher** (`core/file_watcher.py`): Uses watchdog + `DebouncedFileHandler` for local changes, `PeriodicChecker` for 60s cloud polling
- **CloudStorage** (`cloud/base.py`): ABC with 7 methods - implement this for new cloud providers
- **BaiduBOS** (`cloud/baidu_bos.py`): Concrete implementation using bce-python-sdk
- **CryptoManager** (`core/crypto.py`): AES-256-GCM encryption, `derive_key()` for SHA256-based key derivation
- **SyncState** (`storage/sync_state.py`): In-memory tracking of local files and cloud metas

### Encryption Modes

- **Encrypted**: Cloud filenames are SHA256 hashes of original filenames, content is AES-256-GCM encrypted
- **Plain**: Cloud filenames are original filenames, content is plain

### Sync Behavior

- Local change detected → 10s debounce → upload to cloud
- Cloud change detected (60s poll) → compare with `_last_cloud_metas` → download if newer
- Conflict: older version renamed with `.conflict-{timestamp}`

## Configuration

Config is JSON with `cloud_type`, `encryption_enabled`, `encryption_key`, and `sync_pairs[]`. Remote paths in `sync_pairs` cannot overlap (validated at startup).

Baidu BOS credentials via env vars: `BOS_ACCESS_KEY_ID`, `BOS_ACCESS_KEY_SECRET`, `BOS_ENDPOINT`.

## Dependencies

- watchdog>=3.0.0 - File system monitoring
- bce-python-sdk>=0.9 - Baidu BOS SDK
- pycryptodome>=3.18 - AES encryption
