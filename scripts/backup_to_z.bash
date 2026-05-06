#!/bin/bash
# ============================================================
# Daily backup: lixinger.db → Z:\马武个人资料\deepseek\investment-system\data\
# Uses C:\tmp as intermediate (WSL ↔ Windows bridge)
# ============================================================
set -euo pipefail

DB="/home/frank/investment-system/data/lixinger.db"
DATE=$(date +%Y%m%d)
TEMP_DB="/mnt/c/tmp/lixinger-${DATE}.db"
TARGET="Z:\\马武个人资料\\deepseek\\investment-system\\data\\lixinger-${DATE}.db"
PS_EXE="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..."
echo "  Source: $DB"
echo "  Temp:   $TEMP_DB"
echo "  Target: $TARGET"

# Step 1: SQLite online backup (faster than VACUUM, consistent snapshot)
mkdir -p /mnt/c/tmp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 1: .backup (this may take a few minutes)..."
sqlite3 "$DB" ".backup '$TEMP_DB'"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 1 done: $(du -h "$TEMP_DB" | cut -f1)"

# Step 2: Copy to Z: drive via PowerShell
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 2: Copying to Z: drive..."
$PS_EXE -NoProfile -Command "Copy-Item -Path 'C:\\tmp\\lixinger-${DATE}.db' -Destination '$TARGET' -Force"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 2 done"

# Step 3: Verify target exists
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 3: Verifying..."
$PS_EXE -NoProfile -Command "if (Test-Path '$TARGET') { \$f = Get-Item '$TARGET'; Write-Host \"OK: \$(\$f.Name) - \$([math]::Round(\$f.Length/1MB,0)) MB - \$(\$f.LastWriteTime)\" } else { Write-Host 'FAILED: target not found'; exit 1 }"

# Step 4: Cleanup intermediate
rm -f "$TEMP_DB"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup done"

# Step 5: Keep only last 7 daily backups
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Step 5: Pruning old backups (keep 7)..."
$PS_EXE -NoProfile -Command "
    \$dir = 'Z:\\马武个人资料\\deepseek\\investment-system\\data'
    \$files = Get-ChildItem \$dir -Filter 'lixinger-*.db' | Sort-Object LastWriteTime -Descending
    if (\$files.Count -gt 7) {
        \$files[7..\$files.Count] | ForEach-Object { 
            Write-Host \"  Removing: \$(\$_.Name)\"
            Remove-Item \$_.FullName -Force 
        }
        Write-Host \"  Kept 7 most recent backups\"
    } else {
        Write-Host \"  \$(\$files.Count) backup(s), no pruning needed\"
    }
"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete!"
