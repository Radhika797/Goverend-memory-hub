'use client';

import { useState, useEffect, useCallback } from 'react';
import { Activity, Database, Server, Cpu, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock, ShieldCheck } from 'lucide-react';

interface DependencyStatus {
  status: string;
  latency_ms?: number;
  message?: string;
  error?: string;
}

interface HealthResponse {
  status: string;
  service: string;
  phase: string;
  timestamp: string;
  dependencies: {
    postgres: DependencyStatus;
    redis: DependencyStatus;
  };
}

export default function CockpitHome() {
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/health`, { cache: 'no-store' });
      if (!res.ok && res.status !== 503 && res.status !== 530) {
        throw new Error(`HTTP Error ${res.status}`);
      }
      const data: HealthResponse = await res.json();
      setHealthData(data);
      setError(null);
      setLastRefreshed(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to connect to API service');
      setHealthData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchHealth();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchHealth, autoRefresh]);

  const getStatusBadge = (statusStr?: string) => {
    switch (statusStr) {
      case 'healthy':
      case 'ok':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Healthy
          </span>
        );
      case 'degraded':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            Degraded
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" />
            Unhealthy
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-gray-100 p-6 md:p-12">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Header Bar */}
        <header className="flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-gray-800 gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white tracking-tight">Governed Memory Hub</h1>
                <p className="text-xs text-gray-400 font-mono mt-0.5">Control Cockpit • Phase 1 Foundation</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`text-xs px-3 py-1.5 rounded-md font-medium border transition-colors ${
                autoRefresh
                  ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-300'
                  : 'bg-gray-800 border-gray-700 text-gray-400'
              }`}
            >
              Auto Refresh: {autoRefresh ? 'ON (10s)' : 'OFF'}
            </button>
            <button
              onClick={fetchHealth}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh Status
            </button>
          </div>
        </header>

        {/* Banner */}
        <div className="p-4 rounded-xl bg-gray-900/60 border border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="w-5 h-5 text-indigo-400" />
            <span className="text-sm text-gray-300">
              System Architecture Status: <span className="font-semibold text-white">Phase 1 Infrastructure Ready</span>
            </span>
          </div>
          {lastRefreshed && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400 font-mono">
              <Clock className="w-3.5 h-3.5" />
              Last Checked: {lastRefreshed.toLocaleTimeString()}
            </div>
          )}
        </div>

        {/* Error Notification */}
        {error && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-3">
            <XCircle className="w-5 h-5 text-rose-400 shrink-0" />
            <div>
              <p className="font-semibold">Unable to fetch system health status</p>
              <p className="text-xs text-rose-300/80 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Health Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

          {/* Service Overall Health Card */}
          <div className="p-6 rounded-2xl bg-gray-900/80 border border-gray-800 flex flex-col justify-between hover:border-gray-700 transition-all">
            <div className="flex items-start justify-between">
              <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Server className="w-6 h-6" />
              </div>
              {getStatusBadge(healthData?.status)}
            </div>

            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white">FastAPI Service</h3>
              <p className="text-xs text-gray-400 font-mono mt-1">
                {healthData?.service || 'Governed Memory Hub API'}
              </p>
              <div className="mt-4 pt-4 border-t border-gray-800/80 text-xs text-gray-400 flex items-center justify-between">
                <span>Phase</span>
                <span className="font-mono text-gray-200">{healthData?.phase || 'Phase 1: Foundation'}</span>
              </div>
            </div>
          </div>

          {/* PostgreSQL Health Card */}
          <div className="p-6 rounded-2xl bg-gray-900/80 border border-gray-800 flex flex-col justify-between hover:border-gray-700 transition-all">
            <div className="flex items-start justify-between">
              <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
                <Database className="w-6 h-6" />
              </div>
              {getStatusBadge(healthData?.dependencies?.postgres?.status)}
            </div>

            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white">PostgreSQL 16</h3>
              <p className="text-xs text-gray-400 font-mono mt-1">
                Relational System of Record
              </p>
              <div className="mt-4 pt-4 border-t border-gray-800/80 text-xs text-gray-400 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span>Latency</span>
                  <span className="font-mono text-emerald-400">
                    {healthData?.dependencies?.postgres?.latency_ms !== undefined
                      ? `${healthData.dependencies.postgres.latency_ms} ms`
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Details</span>
                  <span className="font-mono text-gray-300 truncate max-w-[160px]">
                    {healthData?.dependencies?.postgres?.message || healthData?.dependencies?.postgres?.error || 'Connected'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Redis Health Card */}
          <div className="p-6 rounded-2xl bg-gray-900/80 border border-gray-800 flex flex-col justify-between hover:border-gray-700 transition-all">
            <div className="flex items-start justify-between">
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400">
                <Cpu className="w-6 h-6" />
              </div>
              {getStatusBadge(healthData?.dependencies?.redis?.status)}
            </div>

            <div className="mt-6">
              <h3 className="text-lg font-semibold text-white">Redis Cache</h3>
              <p className="text-xs text-gray-400 font-mono mt-1">
                Session & Queue Store
              </p>
              <div className="mt-4 pt-4 border-t border-gray-800/80 text-xs text-gray-400 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span>Latency</span>
                  <span className="font-mono text-emerald-400">
                    {healthData?.dependencies?.redis?.latency_ms !== undefined
                      ? `${healthData.dependencies.redis.latency_ms} ms`
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Details</span>
                  <span className="font-mono text-gray-300 truncate max-w-[160px]">
                    {healthData?.dependencies?.redis?.message || healthData?.dependencies?.redis?.error || 'PONG'}
                  </span>
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* Raw Payload Section */}
        {healthData && (
          <div className="p-6 rounded-2xl bg-gray-900/40 border border-gray-800">
            <h4 className="text-xs font-mono uppercase tracking-wider text-gray-400 mb-3">
              API /health Response Payload
            </h4>
            <pre className="p-4 rounded-xl bg-black/60 border border-gray-800 text-xs font-mono text-emerald-400 overflow-x-auto">
              {JSON.stringify(healthData, null, 2)}
            </pre>
          </div>
        )}

      </div>
    </div>
  );
}
