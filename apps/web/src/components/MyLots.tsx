import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import { ProviderApi, type LotDto } from '../lib/api';

type Props = {
  /** When this changes, the list is refetched (e.g. after creating a lot). */
  refreshTrigger?: number;
};

export function MyLots({ refreshTrigger = 0 }: Props) {
  const [lots, setLots] = useState<LotDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyLotId, setBusyLotId] = useState<string | null>(null);

  async function fetchLots() {
    setLoading(true);
    setError(null);
    try {
      const list = await ProviderApi.listLots();
      setLots(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLots([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchLots();
  }, [refreshTrigger]);

  async function markReady(lotId: string) {
    setBusyLotId(lotId);
    setError(null);
    try {
      await ProviderApi.prepareReady(lotId, {
        device_ok: true,
        driver_ok: true,
        image_pulled: true,
        inputs_prefetched: true,
      });
      await fetchLots();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyLotId(null);
    }
  }

  async function submitResult(lotId: string) {
    setBusyLotId(lotId);
    setError(null);
    try {
      await ProviderApi.submitResult(lotId, {
        output_root: `out-${Date.now().toString(16)}`,
        item_count: 1000,
        wall_time_seconds: 120,
        raw_gpu_time_seconds: 110,
        logs_uri: `https://example.com/logs/${encodeURIComponent(lotId)}`,
      });
      await fetchLots();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyLotId(null);
    }
  }

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-slate-100">Provider Lots</h3>
        <Button
          variant="outline"
          size="sm"
          className="bg-slate-800 border-slate-700"
          onClick={() => void fetchLots()}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </Button>
      </div>
      {error ? (
        <p className="text-sm text-red-200">{error}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="border-slate-800 hover:bg-slate-800/50">
              <TableHead className="text-slate-300">Lot ID</TableHead>
              <TableHead className="text-slate-300">Status</TableHead>
              <TableHead className="text-slate-300">Job ID</TableHead>
              <TableHead className="text-slate-300">Window</TableHead>
              <TableHead className="text-slate-300">Created</TableHead>
              <TableHead className="text-slate-300">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lots.length === 0 ? (
              <TableRow className="border-slate-800">
                <TableCell colSpan={6} className="text-slate-400 text-sm">
                  {loading
                    ? 'Loading…'
                    : 'No lots yet. Allocate one from the provider control panel.'}
                </TableCell>
              </TableRow>
            ) : (
              lots.map((l) => (
                <TableRow
                  key={l.lot_id}
                  className="border-slate-800 hover:bg-slate-800/50"
                >
                  <TableCell className="font-mono text-slate-200 text-xs">
                    {l.lot_id}
                  </TableCell>
                  <TableCell className="text-slate-200">{l.status}</TableCell>
                  <TableCell className="text-slate-300 text-xs">
                    {l.job_id ?? '—'}
                  </TableCell>
                  <TableCell className="text-slate-300 text-xs">
                    {l.window.region} · {l.window.iso_hour}h · {l.window.sla} ·{' '}
                    {l.window.tier}
                  </TableCell>
                  <TableCell className="text-slate-400 text-xs">
                    {l.created_at}
                  </TableCell>
                  <TableCell className="text-slate-300">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="bg-slate-800 border-slate-700"
                        disabled={busyLotId === l.lot_id || l.status !== 'pending'}
                        onClick={() => void markReady(l.lot_id)}
                      >
                        Ready
                      </Button>
                      <Button
                        size="sm"
                        className="bg-green-700 hover:bg-green-700"
                        disabled={
                          busyLotId === l.lot_id || !['ready', 'running', 'preparing'].includes(l.status)
                        }
                        onClick={() => void submitResult(l.lot_id)}
                      >
                        Submit Result
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
