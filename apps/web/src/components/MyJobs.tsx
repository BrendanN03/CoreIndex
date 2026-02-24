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
import { JobApi, type JobResponseDto } from '../lib/api';

type Props = {
  /** When this changes, the list is refetched (e.g. after creating a job). */
  refreshTrigger?: number;
};

export function MyJobs({ refreshTrigger = 0 }: Props) {
  const [jobs, setJobs] = useState<JobResponseDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchJobs() {
    setLoading(true);
    setError(null);
    try {
      const list = await JobApi.listJobs();
      setJobs(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchJobs();
  }, [refreshTrigger]);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-slate-100">My jobs</h3>
        <Button
          variant="outline"
          size="sm"
          className="bg-slate-800 border-slate-700"
          onClick={() => void fetchJobs()}
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
              <TableHead className="text-slate-300">Job ID</TableHead>
              <TableHead className="text-slate-300">Status</TableHead>
              <TableHead className="text-slate-300">Window</TableHead>
              <TableHead className="text-slate-300">Packages</TableHead>
              <TableHead className="text-slate-300">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow className="border-slate-800">
                <TableCell colSpan={5} className="text-slate-400 text-sm">
                  {loading ? 'Loading…' : 'No jobs yet. Create one from the marketplace (Connect).'}
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((j) => (
                <TableRow
                  key={j.job_id}
                  className="border-slate-800 hover:bg-slate-800/50"
                >
                  <TableCell className="font-mono text-slate-200 text-xs">
                    {j.job_id}
                  </TableCell>
                  <TableCell className="text-slate-200">{j.status}</TableCell>
                  <TableCell className="text-slate-300 text-xs">
                    {j.window.region} · {j.window.iso_hour}h · {j.window.sla} ·{' '}
                    {j.window.tier}
                  </TableCell>
                  <TableCell className="text-slate-200">
                    {j.package_index?.length ?? 0}
                  </TableCell>
                  <TableCell className="text-slate-400 text-xs">
                    {j.created_at}
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
