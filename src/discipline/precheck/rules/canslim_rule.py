"""
检查：CAN SLIM 评分是否达标
数据来源：can_slim_scores
规则类型：软警告（warn）
"""


class CANSLIMRule:
    name = 'canslim'
    display_name = 'CAN SLIM 评分'
    rule_type = 'warn'
    description = '检查该股的 CAN SLIM 综合评分是否达到买入标准'

    parameters = {
        'min_score': 70,
    }

    def check(self, db, stock_code, buy_qty, buy_price, total_capital):
        row = db.execute("""
            SELECT score, grade
            FROM cansim_scores
            WHERE stock_code = ?
            ORDER BY date DESC LIMIT 1
        """, (stock_code,)).fetchone()

        if not row:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': '⚠ 该股无 CAN SLIM 评分数据',
                'detail': {}
            }

        score = row['score'] or 0
        grade = row['grade'] or ''

        if score < self.parameters['min_score']:
            return {
                'rule': self.name,
                'display_name': self.display_name,
                'result': 'warn',
                'message': f'⚠ CAN SLIM 评分 {score} 低于建议最低分 {self.parameters["min_score"]}',
                'detail': {'score': score, 'grade': grade}
            }

        return {
            'rule': self.name,
            'display_name': self.display_name,
            'result': 'pass',
            'message': f'✅ CAN SLIM 评分: {score}（{grade}）',
            'detail': {'score': score, 'grade': grade}
        }
