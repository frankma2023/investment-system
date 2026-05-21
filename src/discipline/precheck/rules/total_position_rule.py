"""
检查：总仓位是否超过上限
规则类型：硬拦截（hard）
"""


class TotalPositionRule:
    name = 'total_position'
    display_name = '总仓位上限'
    rule_type = 'hard'
    description = '检查买入后总持仓占总资金的比例是否超过上限'

    parameters = {
        'max_total_pct': 80,
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        if not total_capital or total_capital <= 0:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ 未设置总资产（去总览页点击💰设置），跳过仓位检查',
                'detail': {}
            }

        # 所有持仓市值
        total_held = db.execute("""
            SELECT SUM(buy_qty * buy_price) AS total_value
            FROM discipline_trades
            WHERE sell_date IS NULL
        """).fetchone()

        held_value = total_held['total_value'] or 0
        new_value = buy_qty * buy_price
        total_value = held_value + new_value
        total_pct = round(total_value / total_capital * 100, 1)

        if total_pct > self.parameters['max_total_pct']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'fail',
                'message': f'🛑 买入后总仓位将达 {total_pct}%，超过上限 {self.parameters["max_total_pct"]}%',
                'detail': {'total_pct': total_pct, 'max': self.parameters['max_total_pct']}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ 总仓位: {total_pct}%（上限 {self.parameters["max_total_pct"]}%）',
            'detail': {'total_pct': total_pct, 'max': self.parameters['max_total_pct']}
        }
