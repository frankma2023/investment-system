#!/usr/bin/env python3
r"""
scripts/backup_db.py — SQLite WAL安全备份

用法：
    python scripts/backup_db.py                        # 备份到 Z:\马武个人资料\... 默认路径
    python scripts/backup_db.py --dest D:\backups       # 指定目标目录
    python scripts/backup_db.py --keep 30               # 保留最近30份备份（默认7份）

原理：
    WAL模式下不能直接cp文件（可能丢数据），必须通过sqlite3.backup() API。
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

# Windows GBK控制台强制UTF-8输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 路径配置 ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = PROJECT_ROOT / "data" / "lixinger.db"

# 默认备份目录
DEFAULT_DEST = Path(r"Z:\马武个人资料\deepseek\investment-system\data")
FALLBACK_DEST = PROJECT_ROOT / "data" / "backups"


def parse_args():
    dest = DEFAULT_DEST
    keep = 7
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--dest" and i + 1 < len(args):
            dest = Path(args[i + 1])
            i += 2
        elif args[i] == "--keep" and i + 1 < len(args):
            keep = int(args[i + 1])
            i += 2
        else:
            i += 1
    return dest, keep


def backup_db(source: Path, dest_dir: Path, keep: int):
    # ── 检查源文件 ──
    if not source.exists():
        print(f"❌ 源数据库不存在: {source}")
        sys.exit(1)

    size_mb = source.stat().st_size / (1024 * 1024)
    print(f"📦 源数据库: {source} ({size_mb:.0f} MB)")

    # ── 确保目标目录存在 ──
    if not dest_dir.exists():
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 创建备份目录: {dest_dir}")
        except (OSError, PermissionError) as e:
            print(f"⚠️ 无法访问 {dest_dir}: {e}")
            dest_dir = FALLBACK_DEST
            dest_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 回退到: {dest_dir}")

    # ── 备份文件名 ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    backup_name = f"lixinger_{timestamp}.db"
    backup_path = dest_dir / backup_name

    # ── WAL Checkpoint → 直接文件复制 ──
    size_mb = source.stat().st_size / (1024 * 1024)
    print(f"🔄 正在备份 ({size_mb:.0f} MB)...")

    try:
        # 1. checkpoint: 把WAL写入主文件，保证完整性
        src_conn = sqlite3.connect(str(source))
        src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        src_conn.close()

        # 2. checkpoint后可安全直接复制（比 backup() API 快很多）
        shutil.copy2(str(source), str(backup_path))

        backup_size = backup_path.stat().st_size / (1024 * 1024)
        print(f"✅ 备份完成: {backup_path} ({backup_size:.0f} MB)")

    except Exception as e:
        print(f"❌ 备份失败: {e}")
        # 清理不完整的文件
        if backup_path.exists():
            backup_path.unlink()
        sys.exit(1)

    # ── 清理旧备份 ──
    backups = sorted(dest_dir.glob("lixinger_*.db"), key=os.path.getmtime, reverse=True)
    if len(backups) > keep:
        for old in backups[keep:]:
            old.unlink()
            print(f"🗑️ 删除旧备份: {old.name}")

    remaining = len(list(dest_dir.glob("lixinger_*.db")))
    print(f"📊 当前保留 {remaining} 份备份")


if __name__ == "__main__":
    dest, keep = parse_args()
    backup_db(SOURCE_DB, dest, keep)
