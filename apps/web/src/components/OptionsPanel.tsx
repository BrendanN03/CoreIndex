import { useEffect, useMemo, useState } from 'react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  OptionsApi,
  type OptionContractResponseDto,
  type OptionOrderBookResponseDto,
  type OptionOrderSideDto,
  type OptionOrderResponseDto,
  type OptionQuoteResponseDto,
  type OptionTradeResponseDto,
  type PositionSideDto,
  type ProductKeyDto,
  type RiskSummaryResponseDto,
  type MarginStressResponseDto,
  type LiquidationResponseDto,
} from '../lib/api';

const gpuBasePrices: Record<string, number> = {
  'RTX 4090': 2.45,
  A100: 4.8,
  H100: 8.95,
  'RTX 3090': 1.2,
};

function formatProductKey(productKey: ProductKeyDto) {
  return `${productKey.region} · ${productKey.iso_hour}h · ${productKey.sla} · ${productKey.tier}`;
}

type Props = {
  selectedGPU: string;
};

export function OptionsPanel({ selectedGPU }: Props) {
  const [region, setRegion] = useState<ProductKeyDto['region']>('us-east');
  const [isoHour, setIsoHour] = useState<number>(new Date().getUTCHours());
  const [sla, setSla] = useState<ProductKeyDto['sla']>('standard');
  const [tier, setTier] = useState<ProductKeyDto['tier']>('standard');
  const [side, setSide] = useState<PositionSideDto>('buy');
  const [optionType, setOptionType] = useState<'call' | 'put'>('call');
  const [forward, setForward] = useState<number>(gpuBasePrices[selectedGPU] ?? 2.45);
  const [strike, setStrike] = useState<number>(gpuBasePrices[selectedGPU] ?? 2.45);
  const [daysToExpiry, setDaysToExpiry] = useState<number>(14);
  const [vol, setVol] = useState<number>(0.6);
  const [rate, setRate] = useState<number>(0.03);
  const [quantity, setQuantity] = useState<number>(10);

  const [quote, setQuote] = useState<OptionQuoteResponseDto | null>(null);
  const [contracts, setContracts] = useState<OptionContractResponseDto[]>([]);
  const [selectedContractId, setSelectedContractId] = useState<string>('');
  const [orderSide, setOrderSide] = useState<OptionOrderSideDto>('buy');
  const [orderTimeInForce, setOrderTimeInForce] = useState<'gtc' | 'ioc' | 'fok'>('gtc');
  const [orderPrice, setOrderPrice] = useState<number>(0.1);
  const [orderQuantity, setOrderQuantity] = useState<number>(5);
  const [orderSubaccountId, setOrderSubaccountId] = useState<string>('main');
  const [orderStrategyTag, setOrderStrategyTag] = useState<string>('baseline');
  const [optionOrders, setOptionOrders] = useState<OptionOrderResponseDto[]>([]);
  const [optionTrades, setOptionTrades] = useState<OptionTradeResponseDto[]>([]);
  const [optionBook, setOptionBook] = useState<OptionOrderBookResponseDto | null>(null);
  const [risk, setRisk] = useState<RiskSummaryResponseDto | null>(null);
  const [stress, setStress] = useState<MarginStressResponseDto | null>(null);
  const [liquidationResult, setLiquidationResult] = useState<LiquidationResponseDto | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pretradeNote, setPretradeNote] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    const base = gpuBasePrices[selectedGPU] ?? 2.45;
    setForward(base);
    setStrike(base);
  }, [selectedGPU]);

  const productKey = useMemo(
    () => ({ region, iso_hour: isoHour, sla, tier }),
    [region, isoHour, sla, tier],
  );

  const timeToExpiryYears = Math.max(1, daysToExpiry) / 365;

  async function refreshContracts() {
    const [nextContracts, nextRisk, nextStress] = await Promise.all([
      OptionsApi.listContracts(productKey),
      OptionsApi.getRisk(),
      OptionsApi.getStress(),
    ]);
    setContracts(nextContracts);
    setRisk(nextRisk);
    setStress(nextStress);
    if (nextContracts.length && !selectedContractId) {
      setSelectedContractId(nextContracts[0].contract_id);
      setOrderPrice(nextContracts[0].premium_per_ngh);
    }
  }

  async function run(action: () => Promise<void>) {
    setIsBusy(true);
    setError(null);
    try {
      await action();
      await refreshContracts();
      if (selectedContractId) {
        await refreshSelectedContract(selectedContractId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function cancelOptionOrder(orderId: string) {
    await run(async () => {
      await OptionsApi.cancelOrder(orderId);
      setStatus(`Cancelled option order ${orderId}`);
    });
  }

  async function amendOptionOrder(orderId: string, currentPrice: number, side: OptionOrderSideDto) {
    await run(async () => {
      const tick = 0.0001;
      const nextPrice = side === 'buy' ? currentPrice + tick : Math.max(0.0001, currentPrice - tick);
      await OptionsApi.amendOrder(orderId, { limit_price_per_ngh: nextPrice });
      setStatus(`Amended option order ${orderId}`);
    });
  }

  async function pretradeOptionOrder() {
    setIsBusy(true);
    setError(null);
    setStatus(null);
    setPretradeNote(null);
    try {
      const check = await OptionsApi.pretrade({
        contract_id: selectedContractId,
        side: orderSide,
        limit_price_per_ngh: orderPrice,
        quantity_ngh: orderQuantity,
        time_in_force: orderTimeInForce,
        subaccount_id: orderSubaccountId.trim() || undefined,
        strategy_tag: orderStrategyTag.trim() || undefined,
      });
      if (check.approved) {
        setPretradeNote(
          `Approved · ${check.account_scope}${check.subaccount_scope ? `/${check.subaccount_scope}` : ''} · est notional $${check.estimated_notional.toFixed(2)} · est margin $${check.estimated_margin.toFixed(2)}`,
        );
      } else {
        setPretradeNote(
          `Rejected (${check.account_scope}${check.subaccount_scope ? `/${check.subaccount_scope}` : ''}): ${check.reasons.join(', ')}`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsBusy(false);
    }
  }

  useEffect(() => {
    void refreshContracts().catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [region, isoHour, sla, tier]);

  async function refreshSelectedContract(contractId: string) {
    const [book, trades, orders] = await Promise.all([
      OptionsApi.getOrderBook(contractId),
      OptionsApi.listTrades(contractId, 20),
      OptionsApi.listOrders(contractId),
    ]);
    setOptionBook(book);
    setOptionTrades(trades);
    setOptionOrders(orders);
  }

  useEffect(() => {
    if (!selectedContractId) {
      setOptionBook(null);
      setOptionTrades([]);
      setOptionOrders([]);
      return;
    }
    void refreshSelectedContract(selectedContractId).catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [selectedContractId]);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-slate-100">Options Pricing and Risk</h3>
          <p className="mt-2 text-sm text-slate-400">
            Quote Black-76 premiums and Greeks, then list product-key option contracts for
            exchange execution.
          </p>
        </div>
        <Badge variant="outline" className="border-indigo-800 text-indigo-300">
          Derivatives
        </Badge>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Region</div>
          <Select value={region} onValueChange={(v) => setRegion(v as ProductKeyDto['region'])}>
            <SelectTrigger className="bg-slate-800 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="us-east">us-east</SelectItem>
              <SelectItem value="us-west">us-west</SelectItem>
              <SelectItem value="eu-central">eu-central</SelectItem>
              <SelectItem value="asia-pacific">asia-pacific</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">ISO hour</div>
          <Input
            type="number"
            min={0}
            max={23}
            value={isoHour}
            onChange={(e) => setIsoHour(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">SLA</div>
          <Select value={sla} onValueChange={(v) => setSla(v as ProductKeyDto['sla'])}>
            <SelectTrigger className="bg-slate-800 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="standard">standard</SelectItem>
              <SelectItem value="premium">premium</SelectItem>
              <SelectItem value="urgent">urgent</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Tier</div>
          <Select value={tier} onValueChange={(v) => setTier(v as ProductKeyDto['tier'])}>
            <SelectTrigger className="bg-slate-800 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="basic">basic</SelectItem>
              <SelectItem value="standard">standard</SelectItem>
              <SelectItem value="premium">premium</SelectItem>
              <SelectItem value="enterprise">enterprise</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Side</div>
          <Select value={side} onValueChange={(v) => setSide(v as PositionSideDto)}>
            <SelectTrigger className="bg-slate-800 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="buy">buy</SelectItem>
              <SelectItem value="sell">sell</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Option type</div>
          <Select value={optionType} onValueChange={(v) => setOptionType(v as 'call' | 'put')}>
            <SelectTrigger className="bg-slate-800 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="call">call</SelectItem>
              <SelectItem value="put">put</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Forward ($/NGH)</div>
          <Input
            type="number"
            min={0.01}
            step={0.01}
            value={forward}
            onChange={(e) => setForward(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Strike ($/NGH)</div>
          <Input
            type="number"
            min={0.01}
            step={0.01}
            value={strike}
            onChange={(e) => setStrike(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Days to expiry</div>
          <Input
            type="number"
            min={1}
            step={1}
            value={daysToExpiry}
            onChange={(e) => setDaysToExpiry(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Implied volatility</div>
          <Input
            type="number"
            min={0.01}
            step={0.01}
            value={vol}
            onChange={(e) => setVol(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Risk-free rate</div>
          <Input
            type="number"
            step={0.001}
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
        <div className="space-y-2">
          <div className="text-xs text-slate-400">Quantity (NGH)</div>
          <Input
            type="number"
            min={1}
            step={1}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
            className="bg-slate-800 border-slate-700"
          />
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-300">
        Product key: <span className="text-slate-100">{formatProductKey(productKey)}</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          className="bg-indigo-600 hover:bg-indigo-700"
          disabled={isBusy}
          onClick={() =>
            void run(async () => {
              const response = await OptionsApi.quote({
                option_type: optionType,
                forward_price_per_ngh: forward,
                strike_price_per_ngh: strike,
                time_to_expiry_years: timeToExpiryYears,
                implied_volatility: vol,
                risk_free_rate: rate,
                quantity_ngh: quantity,
              });
              setQuote(response);
              setStatus('Pricing quote updated');
            })
          }
        >
          Price Option
        </Button>
        <Button
          variant="outline"
          className="bg-slate-800 border-slate-700"
          disabled={isBusy}
          onClick={() =>
            void run(async () => {
              const contract = await OptionsApi.createContract({
                product_key: productKey,
                side,
                option_type: optionType,
                forward_price_per_ngh: forward,
                strike_price_per_ngh: strike,
                time_to_expiry_years: timeToExpiryYears,
                implied_volatility: vol,
                risk_free_rate: rate,
                quantity_ngh: quantity,
              });
              setSelectedContractId(contract.contract_id);
              setOrderPrice(contract.premium_per_ngh);
              setStatus(`Listed contract ${contract.contract_id}`);
            })
          }
        >
          List Contract
        </Button>
      </div>

      {quote ? (
        <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Quoted premium</div>
            <div className="mt-2 text-sm text-slate-400">
              ${quote.premium_per_ngh.toFixed(4)} / NGH
            </div>
            <div className="text-sm text-slate-400">
              Notional premium: ${quote.premium_notional.toFixed(4)}
            </div>
            <div className="text-sm text-slate-500">
              Intrinsic: ${quote.intrinsic_value_per_ngh.toFixed(4)} | Time value: $
              {quote.time_value_per_ngh.toFixed(4)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Greeks</div>
            <div className="mt-2 text-sm text-slate-400">
              Delta {quote.greeks.delta.toFixed(4)} | Gamma {quote.greeks.gamma.toFixed(4)}
            </div>
            <div className="text-sm text-slate-400">
              Vega {quote.greeks.vega.toFixed(4)} | Theta {quote.greeks.theta.toFixed(4)}
            </div>
            <div className="text-sm text-slate-400">Rho {quote.greeks.rho.toFixed(4)}</div>
          </div>
        </div>
      ) : null}

      <div className="mt-5">
        <div className="text-sm text-slate-100">Open contracts for selected product key</div>
        <div className="mt-3 space-y-3">
          {contracts.length ? (
            contracts.map((contract) => (
              <div
                key={contract.contract_id}
                className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-slate-100">
                    {contract.side} {contract.option_type} | K ${contract.strike_price_per_ngh.toFixed(2)}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-slate-700 text-slate-300">
                      {contract.status}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      className="bg-slate-800 border-slate-700"
                      onClick={() => {
                        setSelectedContractId(contract.contract_id);
                        setOrderPrice(contract.premium_per_ngh);
                      }}
                    >
                      Trade
                    </Button>
                  </div>
                </div>
                <div className="mt-2 text-xs text-slate-400">
                  Premium ${contract.premium_per_ngh.toFixed(4)} / NGH | Qty{' '}
                  {contract.quantity_ngh.toFixed(2)} NGH | Total ${contract.premium_notional.toFixed(4)}
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
              No contracts yet for this key.
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-100">Risk and margin</div>
          {risk ? (
            <div className="mt-3 space-y-1 text-sm text-slate-400">
              <div>Account: {risk.owner_id}</div>
              <div>
                Notional usage: ${risk.used_notional.toFixed(2)} / ${risk.max_notional_limit.toFixed(2)}
              </div>
              <div>Notional remaining: ${risk.remaining_notional.toFixed(2)}</div>
              <div>
                Margin usage: ${risk.used_margin.toFixed(2)} / ${risk.max_margin_limit.toFixed(2)}
              </div>
              <div>Margin remaining: ${risk.remaining_margin.toFixed(2)}</div>
              {stress ? (
                <>
                  <div className="pt-2 text-slate-300">
                    Stress PnL ({(stress.price_shock_pct * 100).toFixed(1)}% price,{' '}
                    {(stress.option_vol_shock_pct * 100).toFixed(1)}% vol): $
                    {stress.stressed_unrealized_pnl.toFixed(2)}
                  </div>
                  <div>
                    Stress margin ratio: {stress.stress_margin_ratio.toFixed(2)}x{' '}
                    {stress.margin_call_triggered ? '(margin call)' : ''}
                  </div>
                </>
              ) : null}
              {liquidationResult ? (
                <div className="pt-2 text-amber-300">
                  Liquidation review: cancelled {liquidationResult.cancelled_futures_orders} futures
                  and {liquidationResult.cancelled_option_orders} option orders.
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-slate-800 border-slate-700"
                  disabled={isBusy}
                  onClick={() =>
                    void run(async () => {
                      const s = await OptionsApi.getStress(-0.2, 0.35);
                      setStress(s);
                      setStatus('Updated stress scenario');
                    })
                  }
                >
                  Run Stress
                </Button>
                <Button
                  size="sm"
                  className="bg-rose-700 hover:bg-rose-700"
                  disabled={isBusy}
                  onClick={() =>
                    void run(async () => {
                      const result = await OptionsApi.liquidate('stress_test_liquidation');
                      setLiquidationResult(result);
                      setStatus('Executed liquidation review');
                    })
                  }
                >
                  Run Liquidation Review
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-3 text-sm text-slate-400">Loading risk limits...</div>
          )}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm text-slate-100">Option order entry</div>
            <div className="text-xs text-slate-500">
              {selectedContractId ? selectedContractId.slice(0, 8) : 'Pick a contract'}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            <Select value={orderSide} onValueChange={(v) => setOrderSide(v as OptionOrderSideDto)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="buy">buy</SelectItem>
                <SelectItem value="sell">sell</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="number"
              min={0.0001}
              step={0.0001}
              value={orderPrice}
              onChange={(e) => setOrderPrice(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
            <Input
              type="number"
              min={0.1}
              step={0.1}
              value={orderQuantity}
              onChange={(e) => setOrderQuantity(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
          </div>
          <Button
            className="mt-3 w-full bg-fuchsia-600 hover:bg-fuchsia-700"
            disabled={isBusy || !selectedContractId}
            onClick={() =>
              void run(async () => {
                const order = await OptionsApi.createOrder({
                  contract_id: selectedContractId,
                  side: orderSide,
                  limit_price_per_ngh: orderPrice,
                  quantity_ngh: orderQuantity,
                  time_in_force: orderTimeInForce,
                  subaccount_id: orderSubaccountId.trim() || undefined,
                  strategy_tag: orderStrategyTag.trim() || undefined,
                });
                setStatus(`Placed option order ${order.order_id}`);
              })
            }
          >
            Place Option Order
          </Button>
          <Button
            variant="outline"
            className="mt-2 w-full bg-slate-800 border-slate-700"
            disabled={isBusy || !selectedContractId}
            onClick={() => void pretradeOptionOrder()}
          >
            Pre-trade Check
          </Button>
          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
            <Input
              value={orderSubaccountId}
              onChange={(e) => setOrderSubaccountId(e.target.value)}
              className="bg-slate-800 border-slate-700"
              placeholder="Subaccount (main)"
            />
            <Input
              value={orderStrategyTag}
              onChange={(e) => setOrderStrategyTag(e.target.value)}
              className="bg-slate-800 border-slate-700"
              placeholder="Strategy (baseline)"
            />
          </div>
          <div className="mt-2">
            <Select
              value={orderTimeInForce}
              onValueChange={(v) => setOrderTimeInForce(v as 'gtc' | 'ioc' | 'fok')}
            >
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gtc">GTC</SelectItem>
                <SelectItem value="ioc">IOC</SelectItem>
                <SelectItem value="fok">FOK</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {pretradeNote ? <div className="mt-2 text-xs text-blue-200">{pretradeNote}</div> : null}
        </div>
      </div>

      {selectedContractId ? (
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Option order book</div>
            {optionBook ? (
              <div className="mt-3 space-y-3 text-sm">
                <div>
                  <div className="text-xs uppercase text-slate-500">Bids</div>
                  <div className="mt-1 space-y-1 text-slate-300">
                    {optionBook.bids.length ? (
                      optionBook.bids.slice(0, 5).map((level, idx) => (
                        <div key={`bid-${idx}`} className="flex justify-between">
                          <span>${level.price_per_ngh.toFixed(4)}</span>
                          <span>{level.quantity_ngh.toFixed(2)} NGH</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-500">No bids</div>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase text-slate-500">Asks</div>
                  <div className="mt-1 space-y-1 text-slate-300">
                    {optionBook.asks.length ? (
                      optionBook.asks.slice(0, 5).map((level, idx) => (
                        <div key={`ask-${idx}`} className="flex justify-between">
                          <span>${level.price_per_ngh.toFixed(4)}</span>
                          <span>{level.quantity_ngh.toFixed(2)} NGH</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-500">No asks</div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-3 text-sm text-slate-500">Book unavailable</div>
            )}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Recent option trades</div>
            <div className="mt-3 space-y-2 text-sm text-slate-300">
              {optionTrades.length ? (
                optionTrades.slice(0, 8).map((trade) => (
                  <div key={trade.trade_id} className="rounded-md border border-slate-800 px-3 py-2">
                    <div>
                      ${trade.price_per_ngh.toFixed(4)} x {trade.quantity_ngh.toFixed(2)} NGH
                    </div>
                    <div className="text-xs text-slate-500">{trade.trade_id}</div>
                  </div>
                ))
              ) : (
                <div className="text-slate-500">No trades yet.</div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
            <div className="text-sm text-slate-100">Your option orders</div>
            <div className="mt-3 space-y-2 text-sm text-slate-300">
              {optionOrders.length ? (
                optionOrders.slice(0, 8).map((order) => (
                  <div key={order.order_id} className="rounded-md border border-slate-800 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        {order.side} ${order.limit_price_per_ngh.toFixed(4)} x{' '}
                        {order.remaining_ngh.toFixed(2)} / {order.quantity_ngh.toFixed(2)}
                        {order.strategy_tag ? ` · ${order.strategy_tag}` : ''}
                      </div>
                      {(order.status === 'open' || order.status === 'partially_filled') && (
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            className="bg-slate-800 border-slate-700"
                            disabled={isBusy}
                            onClick={() => void cancelOptionOrder(order.order_id)}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="bg-slate-800 border-slate-700"
                            disabled={isBusy}
                            onClick={() =>
                              void amendOptionOrder(
                                order.order_id,
                                order.limit_price_per_ngh,
                                order.side,
                              )
                            }
                          >
                            Amend
                          </Button>
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">
                      {order.status} · {order.order_id}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-slate-500">No orders yet.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {(status || error) && (
        <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm">
          {status ? <div className="text-emerald-300">{status}</div> : null}
          {error ? <div className="text-red-200">{error}</div> : null}
        </div>
      )}
    </Card>
  );
}
