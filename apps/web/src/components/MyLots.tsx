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

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-slate-100">My lots</h3>
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
            </TableRow>
          </TableHeader>
          <TableBody>
            {lots.length === 0 ? (
              <TableRow className="border-slate-800">
                <TableCell colSpan={5} className="text-slate-400 text-sm">
                  {loading
                    ? 'Loading…'
                    : 'No lots yet. Create one with POST /lots above.'}
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
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
