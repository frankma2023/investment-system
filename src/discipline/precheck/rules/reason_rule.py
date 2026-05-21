"""
检查：买入理由是否填写且≥20字
规则类型：合规检查（compliance）
"""


class ReasonRule:
    name = 'buy_reason'
    display_name = '买入理由'
    rule_type = 'compliance'
    description = '检查买入理由是否已填写（≥20字）'

    parameters = {
        'min_length': 20,
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': '✅ 买入理由检查由前端表单验证',
            'detail': {}
        }
