"""
检查：行业集中度是否过高
规则类型：软警告（warn）
"""


class IndustryConcentrationRule:
    name = 'industry_concentration'
    display_name = '行业集中度'
    rule_type = 'warn'
    description = '检查同申万一级行业的持仓占比是否过高'

    parameters = {
        'max_industry_pct': 30,
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        if not total_capital or total_capital <= 0:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ 未提供总资金信息',
                'detail': {}
            }

        # 获取该股行业
        ind = db.execute(
            "SELECT industry_name FROM stock_sw_industry WHERE stock_code = ?",
            (stock_code,)
        ).fetchone()
        if not ind or not ind['industry_name']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'pass',
                'message': '✅ 无行业数据，跳过检查',
                'detail': {}
            }

        industry = ind['industry_name']

        # 同行业已有持仓
        holdings = db.execute("""
            SELECT t.stock_code, t.buy_qty * t.buy_price AS held_value
            FROM discipline_trades t
            JOIN stock_sw_industry i ON t.stock_code = i.stock_code
            WHERE t.sell_date IS NULL AND i.industry_name = ?
        """, (industry,)).fetchall()

        held_value = sum(h['held_value'] or 0 for h in holdings)
        new_value = buy_qty * buy_price
        total_industry = held_value + new_value
        industry_pct = round(total_industry / total_capital * 100, 1)

        if industry_pct > self.parameters['max_industry_pct']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': f'⚠ {industry}行业持仓将达 {industry_pct}%，超过建议上限 {self.parameters["max_industry_pct"]}%',
                'detail': {'industry': industry, 'industry_pct': industry_pct, 'max': self.parameters['max_industry_pct']}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ 行业集中度: {industry} {industry_pct}%（上限 {self.parameters["max_industry_pct"]}%）',
            'detail': {'industry': industry, 'industry_pct': industry_pct, 'max': self.parameters['max_industry_pct']}
        }
