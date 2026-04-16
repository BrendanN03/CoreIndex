import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import {
  JobApi,
  type FeasibilityResponseDto,
  type JobResponseDto,
} from '../lib/api';

type Props = {
  /** When this changes, the list is refetched (e.g. after creating a job). */
  refreshTrigger?: number;
};

const JOB_LIST_LIMIT = 50;
const FEASIBILITY_CONCURRENCY = 6;

async function mapPool<T, R>(items: T[], poolSize: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = [];
  for (let i = 0; i < items.length; i += poolSize) {
    const slice = items.slice(i, i + poolSize);
    out.push(...(await Promise.all(slice.map(fn))));
  }
  return out;
}

export function MyJobs({ refreshTrigger = 0 }: Props) {
  const [jobs, setJobs] = useState<JobResponseDto[]>([]);
  const [feasibilityByJob, setFeasibilityByJob] = useState<Record<string, FeasibilityResponseDto>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchJobs() {
    setLoading(true);
    setError(null);
    const delays = [0, 80, 200, 450];
    let list: JobResponseDto[] | null = null;
    for (let i = 0; i < delays.length; i++) {
      if (delays[i] > 0) {
        await new Promise((r) => setTimeout(r, delays[i]));
      }
      try {
        list = await JobApi.listJobs(JOB_LIST_LIMIT);
        break;
      } catch (e) {
        if (i === delays.length - 1) {
          setError(e instanceof Error ? e.message : String(e));
          setJobs([]);
          setFeasibilityByJob({});
          setLoading(false);
          return;
        }
      }
    }
    if (!list) {
      setLoading(false);
      return;
    }
    try {
      setJobs(list);
      const entries = await mapPool(list, FEASIBILITY_CONCURRENCY, async (job) => {
        const feas = await JobApi.getFeasibility(job.job_id);
        return [job.job_id, feas] as const;
      });
      setFeasibilityByJob(Object.fromEntries(entries));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setFeasibilityByJob({});
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
        <div className="max-h-[min(22rem,45vh)] overflow-y-auto overscroll-contain rounded-md border border-slate-800">
        <Table>
          <TableHeader>
            <TableRow className="border-slate-800 hover:bg-slate-800/50">
              <TableHead className="text-slate-300">Job ID</TableHead>
              <TableHead className="text-slate-300">Status</TableHead>
              <TableHead className="text-slate-300">Window</TableHead>
              <TableHead className="text-slate-300">Funding</TableHead>
              <TableHead className="text-slate-300">Packages</TableHead>
              <TableHead className="text-slate-300">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow className="border-slate-800">
                <TableCell colSpan={6} className="text-slate-400 text-sm">
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
                    {feasibilityByJob[j.job_id] ? (
                      feasibilityByJob[j.job_id].voucher_gap === 0 ? (
                        <Badge className="bg-emerald-700 text-white hover:bg-emerald-700">
                          funded
                        </Badge>
                      ) : (
                        <div className="space-y-1">
                          <Badge
                            variant="outline"
                            className="border-amber-800 text-amber-300"
                          >
                            gap {feasibilityByJob[j.job_id].voucher_gap.toFixed(2)} NGH
                          </Badge>
                          <div className="text-[11px] text-slate-500">
                            need {feasibilityByJob[j.job_id].ngh_required.toFixed(2)} NGH
                          </div>
                        </div>
                      )
                    ) : (
                      <span className="text-slate-500 text-xs">...</span>
                    )}
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
        </div>
      )}
    </Card>
  );
}
