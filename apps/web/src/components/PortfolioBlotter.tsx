import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import {
  MarketApi,
  OptionsApi,
  type TradingHierarchyResponseDto,
  type TradingSubaccountRiskResponseDto,
  type TraderPortfolioResponseDto,
  type TraderExecutionMetricsResponseDto,
  type RiskProfileResponseDto,
  type StrategyExecutionMetricsResponseDto,
  type StrategyLimitResponseDto,
} from '../lib/api';

function formatProductKey(key: { region: string; iso_hour: number; sla: string; tier: string }) {
  return `${key.region} · ${key.iso_hour}h · ${key.sla} · ${key.tier}`;
}

export function PortfolioBlotter() {
  const [portfolio, setPortfolio] = useState<TraderPortfolioResponseDto | null>(null);
  const [execution, setExecution] = useState<TraderExecutionMetricsResponseDto | null>(null);
  const [strategyMetrics, setStrategyMetrics] = useState<StrategyExecutionMetricsResponseDto | null>(null);
  const [strategyLimits, setStrategyLimits] = useState<StrategyLimitResponseDto[]>([]);
  const [riskProfile, setRiskProfile] = useState<RiskProfileResponseDto | null>(null);
  const [hierarchy, setHierarchy] = useState<TradingHierarchyResponseDto | null>(null);
  const [subaccountLimits, setSubaccountLimits] = useState<TradingSubaccountRiskResponseDto[]>([]);
  const [maxNotionalInput, setMaxNotionalInput] = useState<string>('25000');
  const [maxMarginInput, setMaxMarginInput] = useState<string>('5000');
  const [maxOrderNotionalInput, setMaxOrderNotionalInput] = useState<string>('25000');
  const [strategyLimitTag, setStrategyLimitTag] = useState<string>('baseline');
  const [strategyLimitOrderNotional, setStrategyLimitOrderNotional] = useState<string>('5000');
  const [strategyKillSwitch, setStrategyKillSwitch] = useState<boolean>(false);
  const [subaccountLimitId, setSubaccountLimitId] = useState<string>('main');
  const [subaccountLimitOrderNotional, setSubaccountLimitOrderNotional] = useState<string>('5000');
  const [subaccountKillSwitch, setSubaccountKillSwitch] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [next, nextExecution, nextRisk, nextStrategyMetrics, nextStrategyLimits, nextSubaccounts, nextHierarchy] = await Promise.all([
        MarketApi.getPortfolio(),
        MarketApi.getExecutionMetrics(),
        OptionsApi.getRiskProfile(),
        MarketApi.getStrategyMetrics(),
        OptionsApi.listStrategyLimits(),
        OptionsApi.listSubaccountLimits(),
        OptionsApi.getTradingHierarchy(),
      ]);
      setPortfolio(next);
      setExecution(nextExecution);
      setRiskProfile(nextRisk);
      setStrategyMetrics(nextStrategyMetrics);
      setStrategyLimits(nextStrategyLimits);
      setSubaccountLimits(nextSubaccounts);
      setHierarchy(nextHierarchy);
      setMaxNotionalInput(String(nextRisk.max_notional_limit));
      setMaxMarginInput(String(nextRisk.max_margin_limit));
      setMaxOrderNotionalInput(String(nextRisk.max_order_notional));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveStrategyLimit() {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      await OptionsApi.upsertStrategyLimit({
        strategy_tag: strategyLimitTag.trim() || 'baseline',
        max_order_notional: Number(strategyLimitOrderNotional),
        kill_switch_enabled: strategyKillSwitch,
      });
      const [nextLimits, nextMetrics] = await Promise.all([
        OptionsApi.listStrategyLimits(),
        MarketApi.getStrategyMetrics(),
      ]);
      setStrategyLimits(nextLimits);
      setStrategyMetrics(nextMetrics);
      setStatus('Updated strategy risk limit');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveSubaccountLimit() {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      await OptionsApi.upsertSubaccountLimit({
        subaccount_id: subaccountLimitId.trim() || 'main',
        max_order_notional: Number(subaccountLimitOrderNotional),
        kill_switch_enabled: subaccountKillSwitch,
      });
      const [nextSubaccounts, nextHierarchy] = await Promise.all([
        OptionsApi.listSubaccountLimits(),
        OptionsApi.getTradingHierarchy(),
      ]);
      setSubaccountLimits(nextSubaccounts);
      setHierarchy(nextHierarchy);
      setStatus('Updated subaccount risk limit');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveRiskProfile() {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const next = await OptionsApi.updateRiskProfile({
        max_notional_limit: Number(maxNotionalInput),
        max_margin_limit: Number(maxMarginInput),
        max_order_notional: Number(maxOrderNotionalInput),
      });
      setRiskProfile(next);
      setStatus('Updated risk profile');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function toggleKillSwitch(enabled: boolean) {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const res = await OptionsApi.setKillSwitch(enabled, 'desk_control');
      setRiskProfile((prev) =>
        prev
          ? { ...prev, kill_switch_enabled: res.kill_switch_enabled, updated_at: res.updated_at }
          : prev,
      );
      setStatus(enabled ? 'Kill switch enabled' : 'Kill switch disabled');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-slate-100">Portfolio and PnL Blotter</h3>
          <p className="mt-2 text-sm text-slate-400">
            Aggregated open positions, open order counts, and mark-to-market unrealized PnL.
          </p>
        </div>
        <Button
          variant="outline"
          className="bg-slate-800 border-slate-700"
          onClick={() => void refresh()}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </Button>
      </div>

      {error ? <div className="mt-4 text-sm text-red-200">{error}</div> : null}
      {status ? <div className="mt-4 text-sm text-emerald-300">{status}</div> : null}

      {portfolio ? (
        <>
          <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-sm text-slate-100">Account Risk Controls</div>
              {hierarchy ? (
                <div className="mt-2 text-xs text-slate-500">
                  Org {hierarchy.org_id} | Account {hierarchy.account_id}
                </div>
              ) : null}
              {riskProfile ? (
                <div className="mt-3 space-y-2 text-sm text-slate-300">
                  <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
                    <Input
                      value={maxNotionalInput}
                      onChange={(e) => setMaxNotionalInput(e.target.value)}
                      className="bg-slate-800 border-slate-700"
                    />
                    <Input
                      value={maxMarginInput}
                      onChange={(e) => setMaxMarginInput(e.target.value)}
                      className="bg-slate-800 border-slate-700"
                    />
                    <Input
                      value={maxOrderNotionalInput}
                      onChange={(e) => setMaxOrderNotionalInput(e.target.value)}
                      className="bg-slate-800 border-slate-700"
                    />
                  </div>
                  <div className="text-xs text-slate-500">
                    Notional limit | Margin limit | Per-order notional cap
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="bg-slate-800 border-slate-700"
                      disabled={loading}
                      onClick={() => void saveRiskProfile()}
                    >
                      Save Limits
                    </Button>
                    <Button
                      size="sm"
                      className={
                        riskProfile.kill_switch_enabled
                          ? 'bg-emerald-700 hover:bg-emerald-700'
                          : 'bg-rose-700 hover:bg-rose-700'
                      }
                      disabled={loading}
                      onClick={() => void toggleKillSwitch(!riskProfile.kill_switch_enabled)}
                    >
                      {riskProfile.kill_switch_enabled ? 'Disable Kill Switch' : 'Enable Kill Switch'}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-2 text-sm text-slate-400">Loading profile...</div>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-sm text-slate-100">Execution Quality</div>
              {execution ? (
                <div className="mt-3 space-y-1 text-sm text-slate-300">
                  <div>Futures fill ratio: {(execution.futures_fill_ratio * 100).toFixed(1)}%</div>
                  <div>Options fill ratio: {(execution.option_fill_ratio * 100).toFixed(1)}%</div>
                  <div>Avg adverse slippage: {execution.avg_adverse_slippage_bps.toFixed(2)} bps</div>
                  <div>
                    Avg time to first fill: {execution.avg_time_to_first_fill_seconds.toFixed(2)}s
                  </div>
                </div>
              ) : (
                <div className="mt-2 text-sm text-slate-400">Loading execution metrics...</div>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-sm text-slate-100">Strategy Routing Controls</div>
              <div className="mt-3 space-y-2">
                <Input
                  value={strategyLimitTag}
                  onChange={(e) => setStrategyLimitTag(e.target.value)}
                  className="bg-slate-800 border-slate-700"
                  placeholder="strategy tag"
                />
                <Input
                  value={strategyLimitOrderNotional}
                  onChange={(e) => setStrategyLimitOrderNotional(e.target.value)}
                  className="bg-slate-800 border-slate-700"
                  placeholder="max order notional"
                />
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input
                    type="checkbox"
                    checked={strategyKillSwitch}
                    onChange={(e) => setStrategyKillSwitch(e.target.checked)}
                  />
                  Strategy kill switch
                </label>
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-slate-800 border-slate-700"
                  disabled={loading}
                  onClick={() => void saveStrategyLimit()}
                >
                  Save Strategy Limit
                </Button>
              </div>
              <div className="mt-3 space-y-1 text-xs text-slate-400">
                {strategyLimits.length ? (
                  strategyLimits.slice(0, 4).map((limit) => (
                    <div key={limit.strategy_tag}>
                      {limit.strategy_tag}: ${limit.max_order_notional.toFixed(0)}{' '}
                      {limit.kill_switch_enabled ? '(halted)' : ''}
                    </div>
                  ))
                ) : (
                  <div>No strategy limits yet.</div>
                )}
              </div>
              <div className="mt-3 text-xs text-slate-400">
                {strategyMetrics?.rows?.length ? (
                  strategyMetrics.rows.slice(0, 3).map((row) => (
                    <div key={row.strategy_tag}>
                      {row.strategy_tag}: fut {(row.futures_fill_ratio * 100).toFixed(0)}%, opt{' '}
                      {(row.option_fill_ratio * 100).toFixed(0)}%, slip{' '}
                      {row.avg_adverse_slippage_bps.toFixed(1)} bps
                    </div>
                  ))
                ) : (
                  <div>No strategy execution rows yet.</div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Subaccount Controls</div>
            <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-3">
              <Input
                value={subaccountLimitId}
                onChange={(e) => setSubaccountLimitId(e.target.value)}
                className="bg-slate-800 border-slate-700"
                placeholder="subaccount id"
              />
              <Input
                value={subaccountLimitOrderNotional}
                onChange={(e) => setSubaccountLimitOrderNotional(e.target.value)}
                className="bg-slate-800 border-slate-700"
                placeholder="max order notional"
              />
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={subaccountKillSwitch}
                  onChange={(e) => setSubaccountKillSwitch(e.target.checked)}
                />
                Subaccount kill switch
              </label>
            </div>
            <div className="mt-3">
              <Button
                size="sm"
                variant="outline"
                className="bg-slate-800 border-slate-700"
                disabled={loading}
                onClick={() => void saveSubaccountLimit()}
              >
                Save Subaccount Limit
              </Button>
            </div>
            <div className="mt-3 space-y-1 text-xs text-slate-400">
              {subaccountLimits.length ? (
                subaccountLimits.slice(0, 6).map((limit) => (
                  <div key={limit.subaccount_id}>
                    {limit.subaccount_id}: ${limit.max_order_notional.toFixed(0)}{' '}
                    {limit.kill_switch_enabled ? '(halted)' : ''}
                  </div>
                ))
              ) : (
                <div>No subaccounts configured.</div>
              )}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-xs uppercase text-slate-500">Account</div>
              <div className="mt-1 text-sm text-slate-100">{portfolio.owner_id}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-xs uppercase text-slate-500">Unrealized PnL</div>
              <div
                className={`mt-1 text-sm ${
                  portfolio.unrealized_pnl_total >= 0 ? 'text-emerald-300' : 'text-red-300'
                }`}
              >
                ${portfolio.unrealized_pnl_total.toFixed(4)}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-xs uppercase text-slate-500">Open Orders</div>
              <div className="mt-1 text-sm text-slate-100">
                Futures {portfolio.open_futures_order_count} | Options {portfolio.open_option_order_count}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-xs uppercase text-slate-500">Recent Trades</div>
              <div className="mt-1 text-sm text-slate-100">
                Futures {portfolio.recent_futures_trade_count} | Options {portfolio.recent_option_trade_count}
              </div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-sm text-slate-100">Futures Positions</div>
              <div className="mt-3 space-y-2">
                {portfolio.futures_positions.length ? (
                  portfolio.futures_positions.map((position, idx) => (
                    <div key={`fut-${idx}`} className="rounded-md border border-slate-800 px-3 py-2">
                      <div className="text-sm text-slate-200">{formatProductKey(position.product_key)}</div>
                      <div className="mt-1 text-xs text-slate-400">
                        Qty {position.net_quantity_ngh.toFixed(2)} | Avg {position.avg_entry_price.toFixed(4)} |
                        Last {position.last_price.toFixed(4)}
                      </div>
                      <Badge
                        variant="outline"
                        className={
                          position.unrealized_pnl >= 0
                            ? 'mt-2 border-emerald-800 text-emerald-300'
                            : 'mt-2 border-red-800 text-red-300'
                        }
                      >
                        PnL ${position.unrealized_pnl.toFixed(4)}
                      </Badge>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-slate-500">No futures positions.</div>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
              <div className="text-sm text-slate-100">Option Positions</div>
              <div className="mt-3 space-y-2">
                {portfolio.option_positions.length ? (
                  portfolio.option_positions.map((position) => (
                    <div key={position.contract_id} className="rounded-md border border-slate-800 px-3 py-2">
                      <div className="text-sm text-slate-200">{position.contract_id}</div>
                      <div className="mt-1 text-xs text-slate-400">
                        Qty {position.net_quantity_ngh.toFixed(2)} | Avg {position.avg_entry_premium.toFixed(4)} |
                        Last {position.last_premium.toFixed(4)}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {formatProductKey(position.product_key)}
                      </div>
                      <Badge
                        variant="outline"
                        className={
                          position.unrealized_pnl >= 0
                            ? 'mt-2 border-emerald-800 text-emerald-300'
                            : 'mt-2 border-red-800 text-red-300'
                        }
                      >
                        PnL ${position.unrealized_pnl.toFixed(4)}
                      </Badge>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-slate-500">No option positions.</div>
                )}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="mt-5 text-sm text-slate-400">Load portfolio data to view positions and PnL.</div>
      )}
    </Card>
  );
}
