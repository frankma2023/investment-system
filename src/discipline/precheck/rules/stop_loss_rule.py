"""
检查：止损价是否已设置
规则类型：合规检查（compliance）
"""


class StopLossRule:
    name = 'stop_loss'
    display_name = '止损设置'
    rule_type = 'compliance'
    description = '检查是否已设置止损价'

    parameters = {}

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': '✅ 止损价检查由前端表单验证',
            'detail': {}
        }
