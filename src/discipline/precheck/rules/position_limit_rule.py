"""
检查：单票仓位是否超过上限
规则类型：硬拦截（hard）
"""


class PositionLimitRule:
    name = 'position_limit'
    display_name = '单票仓位上限'
    rule_type = 'hard'
    description = '检查买入后该股票占总资金的比例是否超过上限'

    parameters = {
        'max_position_pct': 20,
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

        # 该股已持有市值
        existing = db.execute("""
            SELECT SUM(buy_qty * buy_price) AS held_value
            FROM discipline_trades
            WHERE stock_code = ? AND sell_date IS NULL
        """, (stock_code,)).fetchone()

        held_value = existing['held_value'] or 0
        new_value = buy_qty * buy_price
        total_value = held_value + new_value
        position_pct = round(total_value / total_capital * 100, 1)

        if position_pct > self.parameters['max_position_pct']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'fail',
                'message': f'🛑 买入后单票仓位将达 {position_pct}%，超过上限 {self.parameters["max_position_pct"]}%',
                'detail': {'position_pct': position_pct, 'max': self.parameters['max_position_pct']}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ 单票仓位: {position_pct}%（上限 {self.parameters["max_position_pct"]}%）',
            'detail': {'position_pct': position_pct, 'max': self.parameters['max_position_pct']}
        }
