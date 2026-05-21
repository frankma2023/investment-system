"""
检查：大盘环境是否允许买入
数据来源：market_direction_daily
规则类型：软警告（warn）
"""
from datetime import datetime


class MarketPhaseRule:
    name = 'market_phase'
    display_name = '大盘环境'
    rule_type = 'warn'
    description = '检查当前大盘阶段和风险级别是否适合买入'

    parameters = {
        'allowed_phases': ['上升趋势', '震荡盘整'],
        'blocked_levels': ['危险'],
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        row = db.execute("""
            SELECT market_phase, risk_level, suggested_position_size
            FROM market_direction_daily
            ORDER BY date DESC LIMIT 1
        """).fetchone()

        if not row:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ 无法获取大盘环境数据',
                'detail': {}
            }

        phase = row['market_phase'] or ''
        risk = row['risk_level'] or ''

        if risk in self.parameters['blocked_levels']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': f'⚠ 大盘风险级别为"{risk}"，强烈不建议买入',
                'detail': {'phase': phase, 'risk_level': risk}
            }

        if phase not in self.parameters['allowed_phases']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': f'⚠ 当前大盘阶段为"{phase}"，需谨慎',
                'detail': {'phase': phase, 'risk_level': risk}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ 大盘环境：{phase}，风险：{risk}',
            'detail': {'phase': phase, 'risk_level': risk}
        }
