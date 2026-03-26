import { Card } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';
import { ExchangeApi, MarketApi, type ExchangeOrderResponseDto, type ProductKeyDto } from '../lib/api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface OrderBookProps {
  selectedGPU: string;
}

interface Order {
  price: number;
  ngh: number;
  total: number;
}

function modelToProductKey(model: string): ProductKeyDto {
  const isoHour = new Date().getUTCHours();
  if (model === 'RTX 3090') return { region: 'us-west', iso_hour: isoHour, sla: 'standard', tier: 'basic' };
  if (model === 'A100') return { region: 'asia-pacific', iso_hour: isoHour, sla: 'premium', tier: 'premium' };
  if (model === 'H100') return { region: 'us-east', iso_hour: isoHour, sla: 'urgent', tier: 'enterprise' };
  return { region: 'eu-central', iso_hour: isoHour, sla: 'standard', tier: 'standard' };
}

const modelBasePrice: Record<string, number> = {
  'RTX 3090': 1.2,
  'RTX 4090': 2.45,
  A100: 4.8,
  H100: 8.95,
};

export function OrderBook({ selectedGPU }: OrderBookProps) {
  const [buyOrders, setBuyOrders] = useState<Order[]>([]);
  const [sellOrders, setSellOrders] = useState<Order[]>([]);
  const [recentTrades, setRecentTrades] = useState<Order[]>([]);
  const [ngh, setNgh] = useState('10');
  const [price, setPrice] = useState('2.45');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [timeInForce, setTimeInForce] = useState<'gtc' | 'ioc' | 'fok'>('gtc');
  const [subaccountId, setSubaccountId] = useState('main');
  const [strategyTag, setStrategyTag] = useState('baseline');
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pretradeNote, setPretradeNote] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [myOrders, setMyOrders] = useState<ExchangeOrderResponseDto[]>([]);

  const productKey = modelToProductKey(selectedGPU);

  async function refreshBook() {
    const [book, trades, orders] = await Promise.all([
      MarketApi.getLiveOrderBook(productKey),
      MarketApi.getLiveTape({ ...productKey, limit: 20 }),
      ExchangeApi.listOrders(productKey),
    ]);

    setBuyOrders(
      book.bids.map((level) => ({
        price: level.price_per_ngh,
        ngh: level.quantity_ngh,
        total: level.price_per_ngh * level.quantity_ngh,
      })),
    );
    setSellOrders(
      book.asks.map((level) => ({
        price: level.price_per_ngh,
        ngh: level.quantity_ngh,
        total: level.price_per_ngh * level.quantity_ngh,
      })),
    );
    setRecentTrades(
      trades.map((trade) => ({
        price: trade.price_per_ngh,
        ngh: trade.quantity_ngh,
        total: trade.notional,
      })),
    );
    setMyOrders(
      orders.filter((o) => o.status === 'open' || o.status === 'partially_filled').slice(0, 12),
    );
  }

  useEffect(() => {
    setPrice((modelBasePrice[selectedGPU] ?? 2.45).toFixed(2));
  }, [selectedGPU]);

  useEffect(() => {
    void refreshBook().catch((e) => setError(e instanceof Error ? e.message : String(e)));
    const interval = setInterval(() => {
      void refreshBook().catch(() => {
        // Keep current UI values if polling fails.
      });
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedGPU]);

  async function placeOrder() {
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      const qty = Number(ngh);
      const px = Number(price);
      if (!qty || qty <= 0 || !px || px <= 0) {
        throw new Error('Enter valid price and NGH size');
      }
      const order = await ExchangeApi.createOrder({
        product_key: productKey,
        side,
        quantity_ngh: qty,
        price_per_ngh: px,
        time_in_force: timeInForce,
        subaccount_id: subaccountId.trim() || undefined,
        strategy_tag: strategyTag.trim() || undefined,
      });
      setStatus(`Order submitted: ${order.side} ${order.quantity_ngh} NGH @ ${order.price_per_ngh.toFixed(2)}`);
      await refreshBook();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  async function runPretradeCheck() {
    setIsBusy(true);
    setError(null);
    setStatus(null);
    setPretradeNote(null);
    try {
      const qty = Number(ngh);
      const px = Number(price);
      const check = await ExchangeApi.pretrade({
        product_key: productKey,
        side,
        quantity_ngh: qty,
        price_per_ngh: px,
        time_in_force: timeInForce,
        subaccount_id: subaccountId.trim() || undefined,
        strategy_tag: strategyTag.trim() || undefined,
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  async function cancelOrder(orderId: string) {
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      await ExchangeApi.cancelOrder(orderId);
      setStatus(`Cancelled order ${orderId}`);
      await refreshBook();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  async function amendOrder(order: ExchangeOrderResponseDto) {
    setIsBusy(true);
    setError(null);
    setStatus(null);
    try {
      const tick = 0.01;
      const nextPrice = order.side === 'buy' ? order.price_per_ngh + tick : Math.max(0.01, order.price_per_ngh - tick);
      const amended = await ExchangeApi.amendOrder(order.order_id, { price_per_ngh: nextPrice });
      setStatus(`Amended ${amended.order_id} to ${amended.price_per_ngh.toFixed(2)}`);
      await refreshBook();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Order Book */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <h3 className="mb-4 text-slate-100">Order Book</h3>
        
        {/* Sell Orders */}
        <div className="mb-4">
          <div className="grid grid-cols-3 gap-2 text-xs text-slate-400 mb-2 px-2">
            <div>Price ($/hr)</div>
            <div className="text-right">NGH</div>
            <div className="text-right">Total ($)</div>
          </div>
          <div className="space-y-1">
            {sellOrders.map((order, i) => (
              <div 
                key={`sell-${i}`}
                className="grid grid-cols-3 gap-2 text-sm p-2 rounded hover:bg-slate-800/50 cursor-pointer relative overflow-hidden"
              >
                <div 
                  className="absolute right-0 top-0 bottom-0 bg-red-950/20"
                  style={{ width: `${Math.min((order.ngh / 200) * 100, 100)}%` }}
                />
                <div className="text-red-400 relative z-10">{order.price.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.ngh.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.total.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Current Price */}
        <div className="py-3 px-2 bg-slate-800 rounded-lg mb-4 text-center">
          <div className="text-2xl text-green-400">
            $
            {(
              recentTrades[0]?.price ??
              buyOrders[0]?.price ??
              sellOrders[0]?.price ??
              0
            ).toFixed(2)}
          </div>
          <div className="text-xs text-slate-400">Current Market Price</div>
        </div>

        {/* Buy Orders */}
        <div>
          <div className="space-y-1">
            {buyOrders.map((order, i) => (
              <div 
                key={`buy-${i}`}
                className="grid grid-cols-3 gap-2 text-sm p-2 rounded hover:bg-slate-800/50 cursor-pointer relative overflow-hidden"
              >
                <div 
                  className="absolute right-0 top-0 bottom-0 bg-green-950/20"
                  style={{ width: `${Math.min((order.ngh / 200) * 100, 100)}%` }}
                />
                <div className="text-green-400 relative z-10">{order.price.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.ngh.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.total.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Trading Panel — buyer only: place buy orders / acquire compute */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <h3 className="mb-4 text-slate-100">Place Order</h3>
        <div className="space-y-4">
          <div>
            <Label>Side</Label>
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                variant={side === 'buy' ? 'default' : 'outline'}
                className={side === 'buy' ? 'bg-green-700 hover:bg-green-700' : 'bg-slate-800 border-slate-700'}
                onClick={() => setSide('buy')}
              >
                Buy
              </Button>
              <Button
                type="button"
                variant={side === 'sell' ? 'default' : 'outline'}
                className={side === 'sell' ? 'bg-red-700 hover:bg-red-700' : 'bg-slate-800 border-slate-700'}
                onClick={() => setSide('sell')}
              >
                Sell
              </Button>
            </div>
          </div>
          <div>
            <Label>Limit Price ($/NGH)</Label>
            <Input 
              type="number" 
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="bg-slate-800 border-slate-700 mt-1"
              step="0.01"
            />
          </div>
          <div>
            <Label>Size (NGH)</Label>
            <Input 
              type="number" 
              value={ngh}
              onChange={(e) => setNgh(e.target.value)}
              className="bg-slate-800 border-slate-700 mt-1"
            />
          </div>
          <div>
            <Label>Time in Force</Label>
            <Select value={timeInForce} onValueChange={(v) => setTimeInForce(v as 'gtc' | 'ioc' | 'fok')}>
              <SelectTrigger className="bg-slate-800 border-slate-700 mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gtc">GTC</SelectItem>
                <SelectItem value="ioc">IOC</SelectItem>
                <SelectItem value="fok">FOK</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Subaccount</Label>
            <Input
              value={subaccountId}
              onChange={(e) => setSubaccountId(e.target.value)}
              className="bg-slate-800 border-slate-700 mt-1"
              placeholder="main"
            />
          </div>
          <div>
            <Label>Strategy Tag</Label>
            <Input
              value={strategyTag}
              onChange={(e) => setStrategyTag(e.target.value)}
              className="bg-slate-800 border-slate-700 mt-1"
              placeholder="baseline"
            />
          </div>
          <div className="p-3 bg-slate-800 rounded-lg">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-slate-400">Order Notional</span>
              <span className="text-slate-100">${(parseFloat(price || '0') * parseFloat(ngh || '0')).toFixed(2)}</span>
            </div>
          </div>
          <Button
            className={`w-full ${side === 'buy' ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'}`}
            disabled={isBusy}
            onClick={() => void placeOrder()}
          >
            {isBusy ? 'Submitting…' : side === 'buy' ? 'Submit Buy Order' : 'Submit Sell Order'}
          </Button>
          <Button
            variant="outline"
            className="w-full bg-slate-800 border-slate-700"
            disabled={isBusy}
            onClick={() => void runPretradeCheck()}
          >
            Pre-trade Check
          </Button>
          {pretradeNote ? <div className="text-xs text-blue-200">{pretradeNote}</div> : null}
          {status ? <div className="text-xs text-emerald-300">{status}</div> : null}
          {error ? <div className="text-xs text-red-200">{error}</div> : null}
        </div>
      </Card>

      {/* Recent Trades */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <h3 className="text-slate-100 mb-3">My Active Orders</h3>
        <div className="space-y-2 mb-6">
          {myOrders.length ? (
            myOrders.map((order) => (
              <div
                key={order.order_id}
                className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm"
              >
                <div className="text-slate-300">
                  {order.side} {order.remaining_ngh.toFixed(2)} / {order.quantity_ngh.toFixed(2)} NGH @ $
                  {order.price_per_ngh.toFixed(2)}
                  {order.strategy_tag ? ` · ${order.strategy_tag}` : ''}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-slate-800 border-slate-700"
                  disabled={isBusy}
                  onClick={() => void cancelOrder(order.order_id)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-slate-800 border-slate-700"
                  disabled={isBusy}
                  onClick={() => void amendOrder(order)}
                >
                  Amend
                </Button>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-500">No active orders for this key.</div>
          )}
        </div>

        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-4 h-4" />
          <h3 className="text-slate-100">Recent Trades</h3>
        </div>
        <div className="space-y-2">
          {recentTrades.map((trade, i) => (
            <div key={i} className="flex justify-between text-sm p-2 hover:bg-slate-800/50 rounded">
              <span className="text-slate-100">${trade.price.toFixed(2)}</span>
              <span className="text-slate-400">{trade.ngh.toFixed(2)} NGH</span>
              <span className="text-slate-500">${trade.total.toFixed(2)}</span>
            </div>
          ))}
          {recentTrades.length === 0 ? (
            <div className="text-sm text-slate-500">No trades yet for this key.</div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}