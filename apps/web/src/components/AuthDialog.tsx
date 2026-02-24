import { useMemo, useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from './ui/dialog';
import { AuthApi, type UserPublicDto } from '../lib/api';

type Props = {
  onLoggedIn: (payload: { accessToken: string; user: UserPublicDto }) => void;
};

export function AuthDialog({ onLoggedIn }: Props) {
  const [open, setOpen] = useState(false);

  const [mode, setMode] = useState<'login' | 'register'>('login');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<'buyer' | 'seller'>('buyer');

  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    const e = email.trim();
    if (!e || !password) return false;
    if (mode === 'register' && password.length < 8) return false;
    return true;
  }, [email, password, mode]);

  async function handleLogin() {
    setIsBusy(true);
    setError(null);
    try {
      const res = await AuthApi.login({ email: email.trim(), password });
      onLoggedIn({ accessToken: res.access_token, user: res.user });
      setOpen(false);
      setPassword('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRegister() {
    setIsBusy(true);
    setError(null);
    try {
      await AuthApi.register({
        email: email.trim(),
        password,
        display_name: displayName.trim() ? displayName.trim() : undefined,
        role,
      });
      // Convenience: auto-login after register.
      const res = await AuthApi.login({ email: email.trim(), password });
      onLoggedIn({ accessToken: res.access_token, user: res.user });
      setOpen(false);
      setPassword('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="bg-slate-800 border-slate-700">
          Login
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-slate-950 border-slate-800 text-slate-100">
        <DialogHeader>
          <DialogTitle>Authentication</DialogTitle>
          <DialogDescription>
            Demo auth backed by the FastAPI in-memory auth endpoints.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={mode}
          onValueChange={(v) => setMode(v as 'login' | 'register')}
          className="w-full"
        >
          <TabsList className="bg-slate-900 border border-slate-800">
            <TabsTrigger value="login">Login</TabsTrigger>
            <TabsTrigger value="register">Register</TabsTrigger>
          </TabsList>

          <TabsContent value="login" className="mt-4 space-y-3">
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Email</div>
              <Input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="bg-slate-900 border-slate-800"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Password</div>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="bg-slate-900 border-slate-800"
              />
            </div>

            {error ? (
              <div className="text-xs text-red-200 bg-red-950/30 border border-red-900/50 rounded-md p-2 whitespace-pre-wrap">
                {error}
              </div>
            ) : null}

            <Button
              className="w-full bg-blue-600 hover:bg-blue-700"
              disabled={isBusy || !canSubmit}
              onClick={() => void handleLogin()}
            >
              {isBusy ? 'Working…' : 'Login'}
            </Button>
          </TabsContent>

          <TabsContent value="register" className="mt-4 space-y-3">
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Email</div>
              <Input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="bg-slate-900 border-slate-800"
              />
            </div>

            <div className="space-y-2">
              <div className="text-xs text-slate-400">Display name (optional)</div>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Alice"
                className="bg-slate-900 border-slate-800"
              />
            </div>

            <div className="space-y-2">
              <div className="text-xs text-slate-400">Account type</div>
              <Select value={role} onValueChange={(v) => setRole(v as 'buyer' | 'seller')}>
                <SelectTrigger className="bg-slate-900 border-slate-800">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="buyer">Buyer</SelectItem>
                  <SelectItem value="seller">Seller (Provider)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="text-xs text-slate-400">Password (min 8 chars)</div>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="bg-slate-900 border-slate-800"
              />
            </div>

            {error ? (
              <div className="text-xs text-red-200 bg-red-950/30 border border-red-900/50 rounded-md p-2 whitespace-pre-wrap">
                {error}
              </div>
            ) : null}

            <Button
              className="w-full bg-blue-600 hover:bg-blue-700"
              disabled={isBusy || !canSubmit}
              onClick={() => void handleRegister()}
            >
              {isBusy ? 'Working…' : 'Create account'}
            </Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

