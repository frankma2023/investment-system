# Investment System

基于威廉·欧奈尔 CAN SLIM 投资理念的 A 股量化投资系统。

## 功能模块

| 模块 | 功能 | 状态 |
|------|------|:--:|
| M1 大盘扫描 | 抛盘日 / 追盘日 / 吸筹日 / 市场健康度 | 🔴 开发中 |
| M2 行业强度 | 一级行业 RS 排名 | ⏳ 规划中 |
| M3 个股筛选 | CAN SLIM 7 维评分 + 个股 RS | ⏳ 规划中 |
| M4 形态信号 | 杯柄 / 双底 / VCP 等买入卖出形态识别 | ⏳ 规划中 |
| M5 回测看板 | 形态及信号历史回测 | 🟡 抛盘日已完成 |
| M6 持仓管理 | 买入卖出录入 + 自动信号扫描 + 仓位建议 | ⏳ 规划中 |

## 启动

```bash
cd ~/investment-system

# API 服务器 (port 8788)
python3 src/server.py &

# 前端 (port 8772)
python3 -m http.server 8772 --directory web/ &
```

访问：`http://localhost:8772`

## 项目结构

```
investment-system/
├── config/           ← 所有参数配置（YAML）
├── src/              ← Python 后端
│   ├── server.py     ← Flask API 入口
│   ├── detectors/    ← 信号检测器
│   ├── scanners/     ← 扫描器
│   ├── backtest/     ← 回测引擎
│   └── portfolio/    ← 持仓管理
├── web/              ← 前端
│   ├── shared/       ← 共享 CSS/JS
│   └── distribution-day/  ← 抛盘日回测看板
├── docs/product/     ← 产品说明书
├── tests/            ← 测试
└── scripts/          ← 一次性脚本
```

## 技术栈

- 后端：Python + Flask + SQLite
- 前端：Vanilla JS + ECharts
- 数据源：理杏仁 API
- 风格：小红书卡片设计系统 + backtest-dashboard-v1
