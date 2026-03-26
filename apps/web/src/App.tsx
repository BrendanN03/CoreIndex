import { useState } from 'react';
import { MarketOverview } from './components/MarketOverview';
import { PriceChart } from './components/PriceChart';
import { GPUMarketplace } from './components/GPUMarketplace';
import { OrderBook } from './components/OrderBook';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Activity } from 'lucide-react';
import { ProviderSim } from './components/ProviderSim';
import { AuthDialog } from './components/AuthDialog';
import { Button } from './components/ui/button';
import { AuthApi, type UserPublicDto } from './lib/api';
import { Card } from './components/ui/card';
import { MyJobs } from './components/MyJobs';
import { PlatformPhasePanel } from './components/PlatformPhasePanel';
import { MarketPhaseOnePanel } from './components/MarketPhaseOnePanel';
import { OptionsPanel } from './components/OptionsPanel';
import { PortfolioBlotter } from './components/PortfolioBlotter';

export default function App() {
  const [selectedGPU, setSelectedGPU] = useState('RTX 4090');
  const [accessToken, setAccessToken] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem('coreindex_access_token');
  });
  const [user, setUser] = useState<UserPublicDto | null>(() => {
    if (typeof window === 'undefined') return null;
    const raw = window.localStorage.getItem('coreindex_user');
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as Partial<UserPublicDto>;
      if (!parsed.user_id || !parsed.email || !parsed.role) return null;
      return parsed as UserPublicDto;
    } catch {
      return null;
    }
  });

  const signedIn = Boolean(accessToken && user);
  const homeTab = user?.role === 'seller' ? 'provider' : 'buyer';
  const [jobsRefreshTrigger, setJobsRefreshTrigger] = useState(0);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Activity className="w-6 h-6" />
              </div>
              <div>
                <h1>GPU Compute Exchange</h1>
                <p className="text-slate-400 text-sm">Global GPU-Hour Marketplace</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-sm text-slate-400">Market Status</div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="text-green-500">Live</span>
                </div>
              </div>

              {accessToken && user ? (
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="text-sm text-slate-400">Signed in</div>
                    <div className="text-sm text-slate-100">{user.email}</div>
                  </div>
                  <Button
                    variant="outline"
                    className="bg-slate-800 border-slate-700"
                    onClick={() => {
                      window.localStorage.removeItem('coreindex_access_token');
                      window.localStorage.removeItem('coreindex_user');
                      setAccessToken(null);
                      setUser(null);
                    }}
                  >
                    Logout
                  </Button>
                  <Button
                    variant="outline"
                    className="bg-slate-800 border-slate-700"
                    onClick={async () => {
                      try {
                        const me = await AuthApi.me(accessToken);
                        window.localStorage.setItem('coreindex_user', JSON.stringify(me));
                        setUser(me);
                      } catch (e) {
                        // If token is stale, clear it.
                        window.localStorage.removeItem('coreindex_access_token');
                        window.localStorage.removeItem('coreindex_user');
                        setAccessToken(null);
                        setUser(null);
                        console.error(e);
                      }
                    }}
                  >
                    Refresh
                  </Button>
                </div>
              ) : (
                <AuthDialog
                  onLoggedIn={({ accessToken: t, user: u }) => {
                    window.localStorage.setItem('coreindex_access_token', t);
                    window.localStorage.setItem('coreindex_user', JSON.stringify(u));
                    setAccessToken(t);
                    setUser(u);
                  }}
                />
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        <PlatformPhasePanel signedIn={signedIn} role={user?.role ?? null} />

        {!signedIn ? (
          <Card className="mt-6 bg-slate-900 border-slate-800 p-6">
            <h2 className="text-slate-100">Sign in to continue</h2>
            <p className="text-slate-400 text-sm mt-2">
              Register as a <span className="text-slate-200">buyer</span> to see the buyer demo UI,
              or as a <span className="text-slate-200">seller</span> to see the provider demo UI.
            </p>
          </Card>
        ) : (
          <Tabs defaultValue={homeTab} className="mt-6 w-full">
            <TabsList className="bg-slate-900 border border-slate-800">
              {user?.role === 'buyer' ? (
                <TabsTrigger value="buyer">Buyer (demo)</TabsTrigger>
              ) : (
                <TabsTrigger value="provider">Provider (simulated)</TabsTrigger>
              )}
            </TabsList>

            <TabsContent value="buyer" className="mt-6">
              <Tabs defaultValue="futures" className="w-full">
                <TabsList className="bg-slate-900 border border-slate-800">
                  <TabsTrigger value="futures">Futures Desk (primary)</TabsTrigger>
                  <TabsTrigger value="options">Options Desk</TabsTrigger>
                  <TabsTrigger value="advanced">Advanced Market View</TabsTrigger>
                </TabsList>

                <TabsContent value="futures" className="mt-6 space-y-6">
                  <Card className="bg-slate-900 border-slate-800 p-4">
                    <div className="text-slate-100">Quick Start</div>
                    <div className="mt-2 text-sm text-slate-400">
                      Easiest: open Physical Delivery Funding and use <span className="text-slate-200">Run entire demo (one click)</span>
                      (live step progress). Or create a job from the marketplace, buy exposure, then Run Full Demo Flow on a position.
                    </div>
                  </Card>

                  <GPUMarketplace
                    onSelectGPU={setSelectedGPU}
                    selectedGPU={selectedGPU}
                    onJobCreated={() => setJobsRefreshTrigger((k) => k + 1)}
                  />

                  <MyJobs refreshTrigger={jobsRefreshTrigger} />

                  <MarketPhaseOnePanel selectedGPU={selectedGPU} />

                  <PortfolioBlotter />
                </TabsContent>

                <TabsContent value="options" className="mt-6 space-y-6">
                  <OptionsPanel selectedGPU={selectedGPU} />
                </TabsContent>

                <TabsContent value="advanced" className="mt-6 space-y-6">
                  <MarketOverview />
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                    <div className="space-y-6 lg:col-span-2">
                      <PriceChart selectedGPU={selectedGPU} />
                    </div>
                    <div className="lg:col-span-1">
                      <OrderBook selectedGPU={selectedGPU} />
                    </div>
                  </div>
                </TabsContent>
              </Tabs>
            </TabsContent>

            <TabsContent value="provider" className="mt-6">
              <ProviderSim />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
}


