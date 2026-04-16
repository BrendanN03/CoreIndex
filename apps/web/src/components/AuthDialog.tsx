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

/** Relaxed email check (server still validates with EmailStr). Avoids browser-only type=email quirks in dialogs. */
function looksLikeEmail(value: string): boolean {
  const v = value.trim();
  if (!v || v.length > 254) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

export function AuthDialog({ onLoggedIn }: Props) {
  const [open, setOpen] = useState(false);

  const [mode, setMode] = useState<'login' | 'register'>('login');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<'buyer' | 'seller'>('buyer');

  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const registerPasswordHint = useMemo(() => {
    if (mode !== 'register') return null;
    if (!password) return null;
    if (password.length >= 8) return null;
    return `${8 - password.length} more character(s) needed (minimum 8).`;
  }, [mode, password]);

  async function handleLogin() {
    const trimmed = email.trim();
    if (!trimmed) {
      setError('Please enter your email address.');
      return;
    }
    if (!looksLikeEmail(trimmed)) {
      setError('Please enter a valid email address (example: you@company.com).');
      return;
    }
    if (!password) {
      setError('Please enter your password.');
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      const res = await AuthApi.login({ email: trimmed, password });
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
    const trimmed = email.trim();
    if (!trimmed) {
      setError('Please enter your email address.');
      return;
    }
    if (!looksLikeEmail(trimmed)) {
      setError('Please enter a valid email address (example: you@company.com).');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters. Add a few more characters and try again.');
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      await AuthApi.register({
        email: trimmed,
        password,
        display_name: displayName.trim() ? displayName.trim() : undefined,
        role,
      });
      // Convenience: auto-login after register.
      const res = await AuthApi.login({ email: trimmed, password });
      onLoggedIn({ accessToken: res.access_token, user: res.user });
      setOpen(false);
      setPassword('');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (message.toLowerCase().includes('already registered')) {
        setMode('login');
        setError('This email is already registered. Please login with your existing password.');
      } else {
        setError(message);
      }
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" className="bg-slate-800 border-slate-700">
          Login
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-slate-950 border-slate-800 text-slate-100">
        <DialogHeader>
          <DialogTitle>Authentication</DialogTitle>
          <DialogDescription>
            Email/password authentication backed by FastAPI auth endpoints.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={mode}
          onValueChange={(v) => {
            setMode(v as 'login' | 'register');
            setError(null);
          }}
          className="w-full"
        >
          <TabsList className="bg-slate-900 border border-slate-800">
            <TabsTrigger value="login">Login</TabsTrigger>
            <TabsTrigger value="register">Register</TabsTrigger>
          </TabsList>

          <TabsContent value="login" className="mt-4 space-y-3">
            <form
              className="space-y-3"
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                if (!isBusy) void handleLogin();
              }}
            >
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Email</div>
              <Input
                type="text"
                inputMode="email"
                autoComplete="email"
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
                autoComplete="current-password"
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
              type="button"
              className="w-full bg-blue-600 hover:bg-blue-700"
              disabled={isBusy}
              onClick={() => void handleLogin()}
            >
              {isBusy ? 'Working…' : 'Login'}
            </Button>
            </form>
          </TabsContent>

          <TabsContent value="register" className="mt-4 space-y-3">
            <form
              className="space-y-3"
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                if (!isBusy) void handleRegister();
              }}
            >
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Email</div>
              <Input
                type="text"
                inputMode="email"
                autoComplete="email"
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
                <SelectContent position="popper" className="z-[200]">
                  <SelectItem value="buyer">Buyer</SelectItem>
                  <SelectItem value="seller">Seller (Provider)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="text-xs text-slate-400">Password (min 8 chars)</div>
              <Input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="bg-slate-900 border-slate-800"
              />
              {registerPasswordHint ? (
                <div className="text-xs text-amber-200/90">{registerPasswordHint}</div>
              ) : null}
            </div>

            {error ? (
              <div className="text-xs text-red-200 bg-red-950/30 border border-red-900/50 rounded-md p-2 whitespace-pre-wrap">
                {error}
              </div>
            ) : null}

            <Button
              type="button"
              className="w-full bg-blue-600 hover:bg-blue-700"
              disabled={isBusy}
              onClick={() => void handleRegister()}
            >
              {isBusy ? 'Working…' : 'Create account'}
            </Button>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

