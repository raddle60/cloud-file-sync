# cloud-file-sync

本地文件夹与云 BOS 之间的双向同步工具，支持加密和非加密两种模式。

## 功能特性

- **双向同步**：本地与云端双向同步，检测到变更后自动同步
- **加密模式**：AES-256-GCM 加密，云端文件名也被混淆（SHA256 哈希）
- **明文模式**：云端保持原始文件名，方便管理
- **原子操作**：上传/下载均通过临时文件 + 重命名实现，防止数据损坏
- **冲突处理**：双方同时修改时，保留较新版本，旧版本重命名存档
- **云端轮询**：每 60 秒检查云端变更，每 10 秒无本地变化后触发上传

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 配置百度云 BOS 凭证（环境变量）
export BOS_ACCESS_KEY_ID="your-access-key-id"
export BOS_ACCESS_KEY_SECRET="your-access-key-secret"
export BOS_ENDPOINT="http://bj.bcebos.com"  # 或你的地域 endpoint
```

## 使用

```bash
# 启动同步守护进程
PYTHONPATH=src python src/main.py start --config config.json

# 后台运行
PYTHONPATH=src python src/main.py start --config config.json --daemon

# 执行一次同步（不监听文件变化）
PYTHONPATH=src python src/main.py sync --config config.json

# 停止同步
PYTHONPATH=src python src/main.py stop
```

## 配置文件

```json
{
  "cloud_type": "baidu_bos",
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

**字段说明：**
- `cloud_type`：云端引擎类型，目前仅支持 `baidu_bos`
- `encryption_enabled`：是否启用加密（文件名混淆 + 内容加密）
- `encryption_key`：Base64 编码的 32 字节密钥
- `sync_pairs`：同步对列表，remote 路径之间不能相互包含或重叠

## 关键设计

### 架构

插件式云端存储架构，核心引擎与云端适配器解耦：

```
src/
├── main.py              # CLI 入口
├── config/             # 配置加载
├── core/
│   ├── sync_engine.py  # 同步核心引擎
│   ├── file_watcher.py # 文件监听（10s debounce）+ 云端轮询（60s）
│   └── crypto.py       # AES-256-GCM 加密
├── cloud/
│   ├── base.py         # CloudStorage 抽象基类
│   └── baidu_bos.py    # 百度云 BOS 实现
├── models/             # 数据模型
├── meta/               # Meta 文件管理
└── storage/            # 内存同步状态
```
cloud目录下，已抽象公共方法，通过继承base类，实现不同云的同步


### 同步流程

1. **启动时**：扫描本地文件 + 下载云端 meta，全量对比并同步
2. **本地变化**：文件监控系统（watchdog）检测变化，10 秒无新变化后触发增量上传
3. **云端变化**：每 60 秒轮询云端，对比 meta 发现变更后下载到本地

### 云端文件结构

| 模式 | 云端文件名 | 内容 |
|------|-----------|------|
| 加密 | `sha256(原文件名)` | AES-256-GCM 加密 |
| 加密 meta | `sha256(原文件名).meta.json` | AES-256-GCM 加密的 JSON |
| 明文 | `原文件名` | 原始内容 |
| 明文 meta | `原文件名.meta.json` | 明文 JSON |

meta.json 包含：`original_filename`、`size`、`last_modified`、`sha256`

## 隐私保护

### 加密模式

- **文件名**：使用 SHA256 哈希混淆，64 字符十六进制字符串
- **文件内容**：AES-256-GCM 加密，16 字节随机 IV + 密文 + 16 字节认证标签
- **Meta 信息**：同样加密，云端无法得知原始文件名、大小、修改时间

### 明文模式

- 原始文件名和内容以明文形式存储在云端
- 仅包含 `sha256` 哈希用于完整性校验

### 密钥安全

- `encryption_key` 仅存储在本地配置文件，不上传到云端
- 密钥派生：SHA256(password) → 32 字节密钥

### 数据删除

- 删除操作会同步传播到对方
- Meta 文件（`.meta.json`）在云端永不删除，用于记录历史版本
