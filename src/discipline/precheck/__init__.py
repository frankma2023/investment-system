"""
买入前检查清单引擎

借鉴 VnPy RuleTemplate 模式——每条规则独立模块，引擎串行执行，
输出每条规则的 pass/warn/fail 状态。

规则分级：
  hard:       硬拦截 → 触发则不可交易
  warn:       软警告 → 不满足时警告但可继续
  compliance: 合规检查 → 不满足不可提交
"""

from .rules.market_phase_rule import MarketPhaseRule
from .rules.canslim_rule import CANSLIMRule
from .rules.rs_rule import RSRule
from .rules.position_limit_rule import PositionLimitRule
from .rules.total_position_rule import TotalPositionRule
from .rules.industry_rule import IndustryConcentrationRule
from .rules.stop_loss_rule import StopLossRule
from .rules.reason_rule import ReasonRule


class PreTradeChecker:
    """买入前检查清单引擎"""

    def __init__(self):
        self.rules = [
            MarketPhaseRule(),
            CANSLIMRule(),
            RSRule(),
            PositionLimitRule(),
            TotalPositionRule(),
            IndustryConcentrationRule(),
        ]

    def check(self, db, stock_code, buy_qty, buy_price, total_capital=0):
        """
        运行全部检查规则。

        参数:
            db: sqlite3.Connection
            stock_code: 股票代码
            buy_qty: 买入数量
            buy_price: 买入价格
            total_capital: 总资金（用于仓位计算）

        返回:
            {
                'all_pass': bool,       # 全部硬拦截通过
                'all_clean': bool,      # 无任何警告
                'results': [...]        # 每条规则的检查结果
            }
        """
        results = []
        all_pass = True
        all_clean = True

        for rule in self.rules:
            try:
                result = rule.check(db, stock_code, buy_qty, buy_price, total_capital)
            except Exception as e:
                result = {
                    'rule': rule.name,
                    'display_name': rule.display_name,
                    'result': 'error',
                    'message': f'规则执行出错: {e}',
                    'detail': {}
                }
            results.append(result)

            if rule.rule_type == 'hard' and result['result'] == 'fail':
                all_pass = False

            if result['result'] in ('warn', 'fail', 'error'):
                all_clean = False

        return {
            'all_pass': all_pass,
            'all_clean': all_clean,
            'results': results,
        }
