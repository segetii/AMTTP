"""Enterprise validation summary for resolved offline blockers.

Reads the true-OHLC daily SL/TP result set and extracts deployable candidates
under explicit safety filters. This is not paper trading and places no orders.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'daily_geometry_stop_tp_ohlc_results.json'
PLAN = HERE / 'enterprise_trade_plan_latest.json'
OUT = HERE / 'enterprise_validation_summary.json'

SAFETY_FILTERS = {
    'maxdd_floor': -0.45,
    'min_sharpe': 1.25,
    'max_active_rate': 0.15,
    'require_q_at_least': 0.90,
}


def main():
    d = json.loads(RESULTS.read_text())
    rows = d['all_results']
    safe = [r for r in rows
            if r['maxdd'] >= SAFETY_FILTERS['maxdd_floor']
            and r['sharpe'] >= SAFETY_FILTERS['min_sharpe']
            and r['active_rate'] <= SAFETY_FILTERS['max_active_rate']
            and r['q'] >= SAFETY_FILTERS['require_q_at_least']]
    safe = sorted(safe, key=lambda r: (r['maxdd'], r['sharpe'], r['final']), reverse=True)
    plan = json.loads(PLAN.read_text()) if PLAN.exists() else None
    summary = {
        'source': str(RESULTS),
        'safety_filters': SAFETY_FILTERS,
        'safe_candidate_count': len(safe),
        'recommended_daily_risk_setting': safe[0] if safe else None,
        'top_safe_candidates': safe[:10],
        'latest_trade_plan': plan,
        'verdict': 'PASS_OFFLINE_RISK_GATE' if safe else 'FAIL_NO_SAFE_DAILY_SETTING',
        'remaining_before_live': [
            'Paper trading intentionally skipped for now by user request.',
            'Exchange adapter and real order management are not enabled.',
            'K=5 remains research-only; expert cap is K=2 until execution is validated.',
        ],
    }
    OUT.write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))
    print(f"\nSaved -> {OUT}")


if __name__ == '__main__':
    main()
