"""
src/scanners/index_crowding.py — 指数拥挤度计算引擎

基于指数基本面数据（index_fundamental_daily），计算五维度拥挤度指标，
合成复合拥挤度得分（0-100），输出到 index_crowding_daily 表。

维度权重 (v1)：
  交易热度  35%  成交额占比分位 + 换手率分位
  资金流向  25%  融资余额占比分位 + 融资买入额占比分位
  估值水位  25%  PE分位 + PB分位 + 股息率分位
  机构行为  15%  基金重仓分位（缺失时按比例重分配）

运行：
  python src/scanners/index_crowding.py                  # 全量计算
  python src/scanners/index_crowding.py --test           # 测试：仅 5 个指数
  python src/scanners/index_crowding.py --date 2026-05-05 # 指定日期
"""

import os
import sys
import sqlite3
import math
from datetime import datetime, timedelta
from collections import defaultdict

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "lixinger.db")

# 权重配置（可通过外部参数覆盖）
DEFAULT_WEIGHTS = {
    "turnover_ratio":   0.25,   # 成交额占比分位点
    "turnover_rate":    0.10,   # 换手率分位点
    "margin_balance":   0.15,   # 融资余额占比分位点
    "margin_buy":       0.10,   # 融资买入额占比分位点
    "pe_pct":           0.15,   # PE 十年分位点
    "pb_pct":           0.05,   # PB 十年分位点
    "dyr_pct":          0.05,   # 股息率十年分位点
    "fund_holding":     0.15,   # 基金重仓分位点（缺失时按比例重分配）
}

# 滚动窗口（交易日）
ROLLING_WINDOW = 120

# 拥挤等级阈值
DEFAULT_LEVELS = [
    (0,  30, "低拥挤"),
    (30, 60, "正常"),
    (60, 80, "偏高"),
    (80, 101, "高拥挤"),
]

# 数据库表
CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS index_crowding_daily (
    stock_code        TEXT NOT NULL,
    date              TEXT NOT NULL,
    -- 交易热度
    turnover_ratio     REAL,   -- 成交额占比（指数成交额/全市场成交额）
    turnover_ratio_pct REAL,   -- 成交额占比滚动分位点 (0~1)
    turnover_rate_pct  REAL,   -- 换手率滚动分位点 (0~1)
    heat_score         REAL,   -- 交易热度维度得分 (0~100)
    -- 资金流向
    margin_balance_ratio  REAL, -- 融资余额/自由流通市值
    margin_balance_pct    REAL, -- 融资余额占比分位点 (0~1)
    margin_buy_ratio      REAL, -- 融资买入额/成交额
    margin_buy_pct        REAL, -- 融资买入额占比分位点 (0~1)
    flow_score            REAL, -- 资金流向维度得分 (0~100)
    -- 估值水位
    pe_pct            REAL,   -- PE 十年分位点 (0~1)
    pb_pct            REAL,   -- PB 十年分位点 (0~1)
    dyr_pct           REAL,   -- 股息率十年分位点 (0~1)
    valuation_score   REAL,   -- 估值水位维度得分 (0~100)
    -- 机构行为
    fund_holding_pct  REAL,   -- 基金重仓分位点 (0~1)
    institution_score REAL,   -- 机构行为维度得分 (0~100)
    -- 综合
    composite_score   REAL,   -- 复合拥挤度得分 (0~100)
    crowd_level       TEXT,   -- 拥挤等级
    updated_at        TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date)
)"""

UPSERT_SQL = """INSERT OR REPLACE INTO index_crowding_daily
    (stock_code, date, turnover_ratio, turnover_ratio_pct, turnover_rate_pct,
     heat_score, margin_balance_ratio, margin_balance_pct, margin_buy_ratio,
     margin_buy_pct, flow_score, pe_pct, pb_pct, dyr_pct, valuation_score,
     fund_holding_pct, institution_score, composite_score, crowd_level)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


# ════════════════════════════════════════════════════════
# 数据加载
# ════════════════════════════════════════════════════════

def load_data(conn, date=None):
    """加载指数基本面数据，按指数和日期组织。
    返回: {
        stock_code: [(date, mc, tv, ta, to_r, pe_pct, pb_pct, dyr_pct, fpa, fb, ecmc), ...]
    }
    以及全市场成交额序列（用于占比计算的分母）。
    """
    query = """SELECT stock_code, date, mc, tv, ta, to_r,
                      pe_ttm_pct, pb_pct, dyr_pct, fpa, fb, ecmc
               FROM index_fundamental_daily"""
    params = []
    if date:
        query += " WHERE date <= ?"
        params.append(date)

    query += " ORDER BY stock_code, date"

    rows = conn.execute(query, params).fetchall()

    # 按指数分组
    data = defaultdict(list)
    market_ta = []  # 全市场成交额序列

    for r in rows:
        code = r["stock_code"]
        data[code].append((
            r["date"], r["mc"], r["tv"], r["ta"], r["to_r"],
            r["pe_ttm_pct"], r["pb_pct"], r["dyr_pct"],
            r["fpa"], r["fb"], r["ecmc"]
        ))
        if code == "000985":  # 中证全指
            market_ta.append((r["date"], r["ta"]))

    return data, market_ta


# ════════════════════════════════════════════════════════
# 分位点计算
# ════════════════════════════════════════════════════════

def rolling_percentile(values, window=ROLLING_WINDOW):
    """对序列计算滚动分位点"""
    result = []
    for i, (_, v) in enumerate(values):
        if v is None:
            result.append(None)
            continue
        start = max(0, i - window + 1)
        window_vals = [x[1] for x in values[start:i+1] if x[1] is not None]
        if len(window_vals) < max(20, window // 3):
            result.append(None)
            continue
        sorted_vals = sorted(window_vals)
        rank = sum(1 for x in sorted_vals if x < v)
        pct = rank / len(sorted_vals)
        result.append(pct)
    return result


# ════════════════════════════════════════════════════════
# 单指数拥挤度计算
# ════════════════════════════════════════════════════════

def calc_crowding(index_data, market_ta_dict, weights=None, levels=None):
    """
    计算单个指数的拥挤度序列。
    weights: 权重 dict，默认使用 DEFAULT_WEIGHTS
    levels: 等级阈值列表，默认使用 DEFAULT_LEVELS
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if levels is None:
        levels = DEFAULT_LEVELS
    n = len(index_data)
    if n < ROLLING_WINDOW // 2:
        return []

    # ── 计算各子指标原始值 ──
    dates = [d[0] for d in index_data]
    mc_vals = [d[1] for d in index_data]
    ta_vals = [d[3] for d in index_data]
    to_r_vals = [d[4] for d in index_data]
    pe_pct_vals = [d[5] for d in index_data]
    pb_pct_vals = [d[6] for d in index_data]
    dyr_pct_vals = [d[7] for d in index_data]
    fpa_vals = [d[8] for d in index_data]
    fb_vals = [d[9] for d in index_data]
    ecmc_vals = [d[10] for d in index_data]

    # 成交额占比序列
    ta_ratio_vals = []
    for i, d in enumerate(dates):
        mt = market_ta_dict.get(d)
        if mt and mt > 0 and ta_vals[i]:
            ta_ratio_vals.append((d, ta_vals[i] / mt))
        else:
            ta_ratio_vals.append((d, None))

    # 换手率（直接用原始值做分位）
    to_r_seq = list(zip(dates, to_r_vals))

    # 融资余额占比 = fb / ecmc
    margin_balance_ratio = []
    for i, d in enumerate(dates):
        if fb_vals[i] and ecmc_vals[i] and ecmc_vals[i] > 0:
            margin_balance_ratio.append((d, fb_vals[i] / ecmc_vals[i]))
        else:
            margin_balance_ratio.append((d, None))

    # 融资买入额占比 = fpa / ta
    margin_buy_ratio = []
    for i, d in enumerate(dates):
        if fpa_vals[i] and ta_vals[i] and ta_vals[i] > 0:
            margin_buy_ratio.append((d, fpa_vals[i] / ta_vals[i]))
        else:
            margin_buy_ratio.append((d, None))

    # ── 计算滚动分位点 ──
    ta_ratio_pct = rolling_percentile(ta_ratio_vals)
    to_r_pct = rolling_percentile(to_r_seq)
    mb_pct = rolling_percentile(margin_balance_ratio)
    mby_pct = rolling_percentile(margin_buy_ratio)

    # ── 逐日合成 ──
    results = []
    for i in range(n):
        # 收集可用子指标
        indicators = {}

        if ta_ratio_pct[i] is not None:
            indicators["turnover_ratio"] = ta_ratio_pct[i]
        if to_r_pct[i] is not None:
            indicators["turnover_rate"] = to_r_pct[i]
        if mb_pct[i] is not None:
            indicators["margin_balance"] = mb_pct[i]
        if mby_pct[i] is not None:
            indicators["margin_buy"] = mby_pct[i]
        if pe_pct_vals[i] is not None:
            indicators["pe_pct"] = pe_pct_vals[i]
        if pb_pct_vals[i] is not None:
            indicators["pb_pct"] = pb_pct_vals[i]
        if dyr_pct_vals[i] is not None:
            indicators["dyr_pct"] = dyr_pct_vals[i]
        # fund_holding 暂无数据

        if not indicators:
            continue

        # 权重重新分配：仅对可用指标按比例缩放
        available_weight = sum(weights[k] for k in indicators)
        if available_weight == 0:
            continue

        # 计算复合得分（0-100）
        composite = 0
        for key, pct_val in indicators.items():
            scaled_weight = weights[key] / available_weight
            composite += pct_val * scaled_weight * 100

        # 拥挤等级
        level = "未知"
        for lo, hi, label in levels:
            if lo <= composite < hi or (hi == 100 and composite >= lo):
                level = label
                break

        # 维度得分
        heat_score = _dim_score(indicators, ["turnover_ratio", "turnover_rate"], weights)
        flow_score = _dim_score(indicators, ["margin_balance", "margin_buy"], weights)
        val_score = _dim_score(indicators, ["pe_pct", "pb_pct", "dyr_pct"], weights)
        inst_score = _dim_score(indicators, ["fund_holding"], weights)

        results.append({
            "date": dates[i],
            "turnover_ratio": ta_ratio_vals[i][1],
            "turnover_ratio_pct": ta_ratio_pct[i],
            "turnover_rate_pct": to_r_pct[i],
            "heat_score": heat_score,
            "margin_balance_ratio": margin_balance_ratio[i][1],
            "margin_balance_pct": mb_pct[i],
            "margin_buy_ratio": margin_buy_ratio[i][1],
            "margin_buy_pct": mby_pct[i],
            "flow_score": flow_score,
            "pe_pct": pe_pct_vals[i],
            "pb_pct": pb_pct_vals[i],
            "dyr_pct": dyr_pct_vals[i],
            "valuation_score": val_score,
            "fund_holding_pct": None,
            "institution_score": inst_score,
            "composite_score": round(composite, 2),
            "crowd_level": level,
        })

    return results


def _dim_score(indicators, keys, weights=None):
    """计算某个维度的得分（0-100），对可用指标按权重计算"""
    if weights is None:
        weights = DEFAULT_WEIGHTS
    dim_weights = {k: weights[k] for k in keys if k in indicators}
    if not dim_weights:
        return None
    total_w = sum(dim_weights.values())
    if total_w == 0:
        return None
    score = sum(indicators[k] * w / total_w * 100 for k, w in dim_weights.items())
    return round(score, 2)


# ════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════

def run(target_date=None, test_mode=False):
    """执行拥挤度计算（使用默认权重）"""
    _run_internal(target_date, test_mode, DEFAULT_WEIGHTS, DEFAULT_LEVELS)


def _run_internal(target_date, test_mode, weights, levels):
    """内部执行函数，支持自定义权重和等级"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 建表
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    # 加载数据
    print(f"加载指数基本面数据...")
    data, market_ta = load_data(conn, target_date)

    if "000985" not in data:
        print("错误: 缺少中证全指 (000985) 数据，无法计算成交额占比")
        conn.close()
        return

    # 构建全市场成交额字典
    market_ta_dict = {d: ta for d, ta in market_ta}
    print(f"全市场成交额数据: {len(market_ta_dict)} 天")

    # 确定要处理的指数
    index_codes = sorted(data.keys())
    if test_mode:
        # 测试模式：选 5 个代表性指数
        test_codes = []
        for code in ["000985", "000001", "000016", "000300", "000986", "000990", "399006"]:
            if code in index_codes:
                test_codes.append(code)
        index_codes = test_codes[:5]
        print(f"测试模式: {len(index_codes)} 个指数")

    print(f"开始计算 {len(index_codes)} 个指数拥挤度...")
    total_rows = 0

    for idx, code in enumerate(index_codes):
        index_data = data[code]
        results = calc_crowding(index_data, market_ta_dict, weights, levels)

        # 写入数据库
        rows = []
        for r in results:
            rows.append((
                code, r["date"],
                r["turnover_ratio"], r["turnover_ratio_pct"], r["turnover_rate_pct"],
                r["heat_score"],
                r["margin_balance_ratio"], r["margin_balance_pct"], r["margin_buy_ratio"],
                r["margin_buy_pct"], r["flow_score"],
                r["pe_pct"], r["pb_pct"], r["dyr_pct"], r["valuation_score"],
                r["fund_holding_pct"], r["institution_score"],
                r["composite_score"], r["crowd_level"],
            ))

        if rows:
            conn.executemany(UPSERT_SQL, rows)
            conn.commit()
            total_rows += len(rows)

        if (idx + 1) % 50 == 0 or idx == 0:
            sample = results[-1] if results else None
            if sample:
                print(f"  [{idx+1}/{len(index_codes)}] {code} "
                      f"最新 {sample['date']} 拥挤度={sample['composite_score']:.0f} "
                      f"({sample['crowd_level']})")

    conn.close()
    print(f"完成！共 {total_rows} 行写入 index_crowding_daily")


# ════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="计算指数拥挤度")
    parser.add_argument("--test", action="store_true", help="测试模式：仅 5 个指数")
    parser.add_argument("--date", type=str, default=None, help="指定截止日期 YYYY-MM-DD")
    args = parser.parse_args()

    run(target_date=args.date, test_mode=args.test)


# ════════════════════════════════════════════════════════
# YAML 配置加载（供 API 调用）
# ════════════════════════════════════════════════════════

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "index_crowding.yaml")

def load_config():
    """从 index_crowding.yaml 加载配置"""
    if not os.path.exists(CONFIG_PATH):
        return {"weights": DEFAULT_WEIGHTS, "levels": _levels_to_dict(DEFAULT_LEVELS)}
    with open(CONFIG_PATH, encoding='utf-8') as f:
        import yaml
        return yaml.safe_load(f)


def save_config(config_dict):
    """保存配置到 index_crowding.yaml"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        import yaml
        yaml.dump(config_dict, f, allow_unicode=True, default_flow_style=False)


def _levels_to_dict(levels):
    return {"low_max": levels[0][1], "normal_max": levels[1][1], "elevated_max": levels[2][1]}


def compute_for_api(index_codes, start_date, end_date, weights=None, levels=None):
    """
    供 API 调用的计算函数。
    返回: [{stock_code, name, latest_score, latest_level, heat_score, ...}, ...]
    以及历史序列 [{stock_code, dates[], scores[]}, ...]
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if levels is None:
        levels = DEFAULT_LEVELS

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 加载数据
    data, market_ta = load_data(conn)
    market_ta_dict = {d: ta for d, ta in market_ta}

    # 指数名称映射
    try:
        import yaml
        with open(os.path.join(PROJECT_ROOT, "config", "index_rs.yaml"), encoding='utf-8') as f:
            idx_data = yaml.safe_load(f)
        name_map = {}
        for cat_name, idx_list in idx_data.get("categories", {}).items():
            for item in idx_list:
                name_map[item["code"]] = item["name"]
    except Exception:
        name_map = {}

    results = []
    for code in index_codes:
        if code not in data:
            continue
        index_data = data[code]
        
        # 过滤日期范围
        filtered = [(d, mc, tv, ta, to_r, pe, pb, dyr, fpa, fb, ecmc)
                    for (d, mc, tv, ta, to_r, pe, pb, dyr, fpa, fb, ecmc) in index_data
                    if start_date <= d <= end_date]
        if len(filtered) < 20:
            continue

        crowding = calc_crowding(filtered, market_ta_dict, weights, levels)
        if not crowding:
            continue

        latest = crowding[-1]
        results.append({
            "stock_code": code,
            "name": name_map.get(code, code),
            "date": latest["date"],
            "composite_score": latest["composite_score"],
            "crowd_level": latest["crowd_level"],
            "heat_score": latest["heat_score"],
            "flow_score": latest["flow_score"],
            "valuation_score": latest["valuation_score"],
            "institution_score": latest.get("institution_score"),
            "pe_pct": latest["pe_pct"],
            "pb_pct": latest["pb_pct"],
            "turnover_ratio_pct": latest["turnover_ratio_pct"],
            "turnover_rate_pct": latest["turnover_rate_pct"],
            "margin_balance_pct": latest["margin_balance_pct"],
            "margin_buy_pct": latest["margin_buy_pct"],
        })

    conn.close()

    # 按拥挤度降序排列
    results.sort(key=lambda x: x["composite_score"] or 0, reverse=True)
    return results
