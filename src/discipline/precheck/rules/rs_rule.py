"""
检查：RS 强度是否在市场中排名靠前
数据来源：stock_rs_daily
规则类型：软警告（warn）
"""


class RSRule:
    name = 'rs_strength'
    display_name = 'RS 强度'
    rule_type = 'warn'
    description = '检查该股的 RS 强度排名是否在市场前 20%'

    parameters = {
        'min_rps_20': 80,
        'min_rps_250': 70,
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        row = db.execute("""
            SELECT rps_20, rps_250
            FROM stock_rs_daily
            WHERE stock_code = ?
            ORDER BY date DESC LIMIT 1
        """, (stock_code,)).fetchone()

        if not row:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ 该股无 RS 数据',
                'detail': {}
            }

        rps_20 = row['rps_20'] or 0
        rps_250 = row['rps_250'] or 0

        warnings = []
        if rps_20 < self.parameters['min_rps_20']:
            warnings.append(f'RPS_20={rps_20}（建议≥{self.parameters["min_rps_20"]}）')
        if rps_250 < self.parameters['min_rps_250']:
            warnings.append(f'RPS_250={rps_250}（建议≥{self.parameters["min_rps_250"]}）')

        if warnings:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ RS 强度不足: ' + '; '.join(warnings),
                'detail': {'rps_20': rps_20, 'rps_250': rps_250}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ RS 强度: RPS_20={rps_20}, RPS_250={rps_250}',
            'detail': {'rps_20': rps_20, 'rps_250': rps_250}
        }
