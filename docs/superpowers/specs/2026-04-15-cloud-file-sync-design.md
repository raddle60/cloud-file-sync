# 云端双向同步工具 - 设计文档

## 1. 项目概述

**项目名称**: cloud-file-sync
**项目类型**: Python CLI 工具（无GUI）
**核心功能**: 本地文件夹与云端存储之间的双向同步，支持加密和非加密两种模式
**目标用户**: 需要在本地和云端之间同步文件的开发者/用户

---

## 2. 核心设计决策

| 决策项 | 选择 |
|--------|------|
| 同步模式 | 双向同步 |
| Meta文件位置 | 仅存在于云端，本地meta信息仅在内存中 |
| 云端架构 | 插件式架构，内置百度云BOS实现 |
| 同步触发 | Daemon模式持续监听，10秒无修改后触发同步 |
| 冲突处理 | 保留双方版本，用时间戳判断新旧，重命名旧版本 |
| 删除策略 | 单向删除传播，meta文件永不删除 |
| 启动模式 | 启动时全量对比本地与云端 |
| 加密算法 | AES-256-GCM |
| 配置格式 | JSON |

---

## 3. 架构设计

```
cloud_file_sync/
├── main.py                     # 程序入口
├── config/
│   └── config_loader.py        # 配置文件加载
├── core/
│   ├── sync_engine.py          # 同步核心引擎
│   ├── file_watcher.py         # 文件监听（debounce 10s）
│   ├── crypto.py               # AES-256-GCM 加解密
│   └── conflict_resolver.py    # 冲突处理
├── cloud/
│   ├── base.py                 # 云端存储抽象接口
│   └── baidu_bos.py            # 百度云BOS实现
├── models/
│   └── sync_pair.py            # 同步对数据模型
├── meta/
│   └── meta_manager.py         # Meta文件管理
└── storage/
    └── sync_state.py           # 本地同步状态（内存）
```

---

## 4. 配置文件结构

```json
{
  "encryption_enabled": true,
  "encryption_key": "your-32-byte-base64-key",
  "sync_pairs": [
    {
      "local": "/path/to/local/folder",
      "remote": "bucket-name/prefix/"
    }
  ]
}
```

**字段说明**:
- `encryption_enabled`: 是否启用加密（同时影响文件名hash和文件内容加密）
- `encryption_key`: Base64编码的32字节密钥
- `sync_pairs`: 同步对列表，支持多目录映射
- 所有同步对共用同一加密密钥

---

## 5. 云端文件命名规则

### 5.1 加密模式（encryption_enabled = true）

| 类型 | 云端文件名 | 内容 |
|------|-----------|------|
| 原文件 | `sha256(original_filename)` | AES-256-GCM加密后的文件内容 |
| Meta文件 | `sha256(original_filename).meta.json` | AES-256-GCM加密的JSON |

### 5.2 非加密模式（encryption_enabled = false）

| 类型 | 云端文件名 | 内容 |
|------|-----------|------|
| 原文件 | `original_filename` | 原始文件内容 |
| Meta文件 | `original_filename.meta.json` | 明文JSON |

### 5.3 文件名Hash规则

- 加密模式下：使用SHA256生成64字符十六进制哈希值
- 非加密模式下：直接使用原始文件名
- 云端tmp文件命名：在最终文件名后加 `.tmp`
  - 加密模式: `sha256(original_filename).tmp`
  - 非加密模式: `original_filename.tmp`

---

## 6. Meta文件结构

每个同步文件在云端对应一个 `.meta.json` 文件：

```json
{
  "original_filename": "document.pdf",
  "size": 1024000,
  "last_modified": 1713187200,
  "sha256": "abc123def456..."
}
```

**字段说明**:
- `original_filename`: 原始文件名
- `size`: 文件大小（字节）
- `last_modified`: 文件最后修改时间（Unix时间戳）
- `sha256`: 文件内容SHA256哈希值

**重要约束**:
- Meta文件在云端永不删除
- Meta文件用于判断文件是否存在及版本新旧

---

## 7. 同步流程

### 7.1 启动流程

```
1. 加载配置文件
2. 初始化云端存储适配器
3. 扫描本地所有文件（递归）
4. 下载云端所有meta文件
5. 全量对比：本地 vs 云端
6. 执行同步（新增/覆盖/删除）
7. 进入Daemon监听模式
```

### 7.2 全量对比逻辑

| 情况 | 处理方式 |
|------|----------|
| 本地有，云端无 | 上传到云端 |
| 本地无，云端有 | 从云端下载 |
| 两边都有，内容不同 | 按时间戳判断新旧，保留新的 |
| 两边都有，时间戳相同sha256不同 | 冲突处理 |

### 7.3 Daemon监听模式

- 使用文件系统监控（如 `watchdog` 库）
- 检测到文件变化后，重置10秒计时器
- 10秒内无新变化，触发同步
- 同步完成后继续监听

---

## 8. 冲突处理流程

当检测到同一文件在本地和云端都有修改，且内容不同时：

```
1. 比较 last_modified 时间戳
2. 较新的文件保留在原位置
3. 较旧的文件重命名：
   - 本地重命名: 原名.conflict-{YYYYMMDD-HHMMSS}
   - 云端重命名: sha256(原名).conflict-{YYYYMMDD-HHMMSS}
4. 同步两个版本到对方位置
```

**示例**:
- 原文件: `report.pdf`
- 冲突后: `report.conflict-20260415-143022.pdf`（较旧版本）
- 云端: `sha256(report.pdf).conflict-20260415-143022`（较旧版本）

---

## 9. 删除处理流程

删除操作需要严格验证，防止误删：

```
1. 检测到文件在一方不存在（但meta存在）
2. 验证删除方：
   a. 本地删除：检查云端meta中的sha256与本地剩余文件（如有）是否相同
   b. 云端删除：下载云端文件比对sha256
3. 验证删除时间 > 文件最后修改时间
4. 确认后执行另一方的删除
5. Meta文件永不删除
```

**删除传播规则**:
- 本地删除 → 同步时云端也删除
- 云端删除 → 同步时本地也删除
- Meta文件在云端永久保留

---

## 10. 云端存储接口抽象

```python
class CloudStorage(ABC):
    @abstractmethod
    def list_files(self, prefix: str) -> List[str]:
        """列出云端所有文件"""
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """下载文件到本地"""
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """上传文件到云端"""
        pass

    @abstractmethod
    def delete_file(self, remote_path: str) -> None:
        """删除云端文件"""
        pass

    @abstractmethod
    def rename_file(self, old_path: str, new_path: str) -> None:
        """重命名云端文件"""
        pass
```

---

## 11. 加密设计

### 11.1 AES-256-GCM加密流程

```
加密:
1. 生成16字节随机IV
2. 使用AES-256-GCM加密文件内容
3. 输出格式: IV (16字节) + 密文 + auth_tag (16字节)

解密:
1. 提取前16字节作为IV
2. 使用密钥和IV解密
3. 验证auth_tag
```

### 11.2 文件名Hash

- 使用SHA256生成64字符哈希值
- 不做base64编码，直接使用十六进制字符串

---

## 12. 原子修改流程

为防止同步过程中数据损坏，所有文件修改采用原子操作。

### 12.1 本地文件修改（从云端下载）

```
1. 将云端文件下载到本地临时文件: 原名.tmp
2. 计算临时文件的sha256值
3. 比对sha256与云端meta中的sha256
4. 若一致：
   a. 删除原本地文件
   b. 将tmp文件重命名为原文件名
5. 若不一致：删除tmp文件，记录错误
```

### 12.2 云端文件上传

```
1. 将本地文件上传到云端临时文件: 目标文件名.tmp
2. 获取云端tmp文件的hash值（如云端支持）
   - 若支持：比对hash与本地sha256
   - 若不支持：比对文件大小
3. 若一致：
   a. 删除云端原文件
   b. 将tmp文件重命名为目标文件名
4. 若不一致：删除云端tmp文件，记录错误
```

### 12.3 云端tmp文件命名

| 模式 | 最终文件名 | tmp文件名 |
|------|-----------|-----------|
| 加密模式 | `sha256(original_filename)` | `sha256(original_filename).tmp` |
| 非加密模式 | `original_filename` | `original_filename.tmp` |

---

## 13. 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| 网络中断 | 重试3次，间隔2秒 |
| 云端认证失败 | 退出并提示 |
| 本地文件被占用 | 跳过并记录，等待下次同步 |
| 磁盘空间不足 | 退出并提示 |
| 加密/解密失败 | 退出并提示 |

---

## 13. 命令行接口

```bash
# 启动同步
python main.py start --config config.json

# 后台运行
python main.py start --config config.json --daemon

# 停止同步
python main.py stop

# 手动触发一次同步
python main.py sync --config config.json
```

---

## 14. 依赖库

```
watchdog>=3.0.0      # 文件系统监控
bce-python-sdk>=0.9  # 百度云BOS SDK
pycryptodome>=3.18   # AES加密
```

---

## 15. 限制与约束

1. 不支持符号链接同步
2. 不支持空文件夹同步（文件夹内无文件时不创建）
3. 不支持大于可用内存的单个文件加密（需流式处理）
4. 配置文件路径不支持加密
5. 仅支持Python 3.9+
