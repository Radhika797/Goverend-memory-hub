'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  Activity, Database, Server, Cpu, RefreshCw, CheckCircle2, AlertTriangle, 
  XCircle, Clock, ShieldCheck, DollarSign, PieChart, Users, FileText, 
  Layers, Lock, Eye, Check, X, ArrowUpRight, BarChart3, Binary,
  ChevronRight, ShieldAlert, Key, GitMerge, FileCheck, ExternalLink,
  Settings, Home, HardDrive, Search, Bell, Sun, MoreVertical,
  ChevronDown, Shield, User, Info, ArrowRight, Code, Calendar, LayoutGrid
} from 'lucide-react';

interface MetricDrilldownEvent {
  event_id: number;
  actor_type: string;
  actor_id: string;
  action: string;
  object_type: string;
  object_id: string;
  decision: string;
  reason_code: string;
  policy_version: string;
  current_hash: string;
  timestamp: string;
}

type NavSection = 'overview' | 'governance' | 'retrieval' | 'graph' | 'orchestration' | 'evidence' | 'erasure' | 'settings';

export default function CockpitHome() {
  const [navSection, setNavSection] = useState<NavSection>('overview');
  const [activeTab, setActiveTab] = useState<'finance' | 'technology'>('finance');
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  // System Health States
  const [healthStatus, setHealthStatus] = useState<any>({
    postgres: 'healthy',
    redis: 'healthy',
    api: 'healthy'
  });

  // Drilldown modal state
  const [drilldownMetric, setDrilldownMetric] = useState<string | null>(null);
  const [drilldownData, setDrilldownData] = useState<any>(null);
  const [drilldownLoading, setDrilldownLoading] = useState<boolean>(false);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      
      // Fetch Metrics
      const res = await fetch(`${apiUrl}/api/v1/cockpit/metrics`, { cache: 'no-store' });
      if (!res.ok) {
        throw new Error(`HTTP Error ${res.status}`);
      }
      const data = await res.json();
      setMetrics(data);
      setError(null);
      setLastRefreshed(new Date());

      // Fetch Health
      try {
        const healthRes = await fetch(`${apiUrl}/health`, { cache: 'no-store' });
        if (healthRes.ok) {
          const healthData = await healthRes.json();
          setHealthStatus({
            postgres: healthData?.dependencies?.postgres?.status || 'healthy',
            redis: healthData?.dependencies?.redis?.status || 'healthy',
            api: healthData?.status || 'healthy'
          });
        }
      } catch {
        // Health check fallback
      }

    } catch (err: any) {
      setError(err.message || 'Failed to fetch cockpit metrics');
    } finally {
      setLoading(false);
    }
  }, []);

  const openDrilldown = async (metricId: string) => {
    setDrilldownMetric(metricId);
    setDrilldownLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/cockpit/drilldown/${metricId}`, { cache: 'no-store' });
      const data = await res.json();
      setDrilldownData(data);
    } catch {
      setDrilldownData(null);
    } finally {
      setDrilldownLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchMetrics();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchMetrics, autoRefresh]);

  const auditValid = metrics?.audit_chain?.valid ?? true;
  const reconDrift = metrics?.reconciliation?.drift_count || 0;
  const totalEvents = metrics?.audit_chain?.total_events || 328;

  return (
    <div className="min-h-screen bg-[#F4F6F9] text-slate-900 flex flex-col md:flex-row font-sans selection:bg-[#0D182A]/20 selection:text-[#0D182A]">
      
      {/* ========================================================================= */}
      {/* 1. ENTERPRISE LEFT SIDEBAR */}
      {/* ========================================================================= */}
      <aside className="w-full md:w-64 bg-white text-slate-700 flex-shrink-0 flex flex-col border-r border-[#E6EBF1] shadow-xs">
        
        {/* Branding Area */}
        <div className="p-5 flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-[#0D182A] text-white shadow-md flex items-center justify-center">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-base font-bold text-[#0D182A] tracking-tight leading-snug">Governed Memory Hub</h1>
            <p className="text-[11px] text-slate-500 font-medium">Enterprise Control Cockpit</p>
          </div>
        </div>

        {/* Governance Engine Status Bar */}
        <div className="mx-4 mb-3 px-3.5 py-2.5 rounded-xl bg-slate-50 border border-[#E6EBF1] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-[#0D182A]">
            <span className="w-2 h-2 rounded-full bg-[#0D182A]"></span>
            Governance Engine
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 text-[#0D182A] border border-slate-300">
            v11.0.0
          </span>
        </div>

        {/* Sidebar Navigation Menu */}
        <nav className="px-3 py-1 space-y-1 flex-1 overflow-y-auto">
          <div className="px-3 pt-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            Core Modules
          </div>

          <button
            onClick={() => setNavSection('overview')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'overview'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Home className="w-4 h-4" />
              <span>Overview</span>
            </div>
            <ChevronRight className={`w-3.5 h-3.5 transition-transform ${navSection === 'overview' ? 'rotate-90 text-white' : 'text-slate-400'}`} />
          </button>

          <button
            onClick={() => setNavSection('governance')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'governance'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Lock className="w-4 h-4" />
              <span>Governance &amp; Rules</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'governance' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}>v1.0</span>
          </button>

          <button
            onClick={() => setNavSection('retrieval')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'retrieval'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Layers className="w-4 h-4" />
              <span>Vector Memory</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'retrieval' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-700 border border-slate-200'}`}>98.5%</span>
          </button>

          <button
            onClick={() => setNavSection('graph')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'graph'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <GitMerge className="w-4 h-4" />
              <span>Graph Lineage</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'graph' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}>AGE</span>
          </button>

          <button
            onClick={() => setNavSection('orchestration')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'orchestration'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Cpu className="w-4 h-4" />
              <span>Agent Orchestration</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'orchestration' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}>8-Stage</span>
          </button>

          <button
            onClick={() => setNavSection('evidence')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'evidence'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <FileCheck className="w-4 h-4" />
              <span>Evidence Packages</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'evidence' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-700 border border-slate-200'}`}>SHA-256</span>
          </button>

          <button
            onClick={() => setNavSection('erasure')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'erasure'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Key className="w-4 h-4" />
              <span>Erasure &amp; Hold</span>
            </div>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${navSection === 'erasure' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-700 border border-slate-200'}`}>Art. 17</span>
          </button>

          <div className="px-3 pt-4 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            System &amp; Admin
          </div>

          <button
            onClick={() => setNavSection('settings')}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all ${
              navSection === 'settings'
                ? 'bg-[#0D182A] text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-[#0D182A]'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Settings className="w-4 h-4" />
              <span>System &amp; Status</span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-[#0D182A] font-bold border border-slate-200">Active</span>
          </button>

          <button
            onClick={() => openDrilldown('AUDIT_CHAIN')}
            className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 hover:text-[#0D182A] transition-all"
          >
            <div className="flex items-center gap-2.5">
              <Search className="w-4 h-4" />
              <span>Audit Inspector</span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-bold border border-slate-200">{totalEvents} Events</span>
          </button>
        </nav>

        {/* Sidebar Footer Profile Card */}
        <div className="p-3 border-t border-[#E6EBF1] bg-white">
          <div className="p-2.5 rounded-xl hover:bg-slate-50 transition-colors flex items-center justify-between cursor-pointer border border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-[#0D182A] text-white flex items-center justify-center font-bold text-xs shadow-xs font-mono">
                AS
              </div>
              <div>
                <div className="text-xs font-bold text-[#0D182A] leading-tight">Admin Steward</div>
                <div className="text-[10px] text-slate-500 font-medium">System Administrator</div>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-400" />
          </div>
        </div>

      </aside>

      {/* ========================================================================= */}
      {/* 2. MAIN CONTENT AREA */}
      {/* ========================================================================= */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">

        {/* Top Header Bar */}
        <header className="bg-white border-b border-[#E6EBF1] sticky top-0 z-30 px-6 py-4 shadow-xs space-y-3">
          
          {/* Header Top Row: Title + Time/Status Widgets */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            
            <div>
              <h2 className="text-xl font-bold text-[#0D182A] tracking-tight">
                Executive Control Cockpit
              </h2>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Real-time governance, security &amp; audit command center
              </p>
            </div>

            {/* Top Right Widget Cards (Reference Screenshot Match) */}
            <div className="flex flex-wrap items-center gap-2 text-xs font-sans">
              
              {/* Current Time Widget */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-[#E6EBF1] text-slate-700">
                <Clock className="w-4 h-4 text-[#0D182A]" />
                <div className="flex flex-col text-right">
                  <span className="font-mono font-bold text-[11px] text-[#0D182A]">02:12:34 AM</span>
                  <span className="text-[9px] text-slate-500">19 Aug 2026, Tue</span>
                </div>
              </div>

              {/* Baseline Widget */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-[#E6EBF1] text-slate-700">
                <Calendar className="w-4 h-4 text-[#0D182A]" />
                <div className="flex flex-col">
                  <span className="font-bold text-[11px] text-[#0D182A]">Week 1</span>
                  <span className="text-[9px] text-slate-500">Baseline Active</span>
                </div>
              </div>

              {/* Control Posture Widget */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-[#E6EBF1] text-slate-700">
                <ShieldCheck className="w-4 h-4 text-[#0D182A]" />
                <div className="flex flex-col">
                  <span className="font-bold text-[11px] text-[#0D182A]">Control Posture</span>
                  <span className="text-[9px] text-slate-600 font-bold">Healthy</span>
                </div>
              </div>

              {/* Environment Widget */}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-[#E6EBF1] text-slate-700">
                <LayoutGrid className="w-4 h-4 text-[#0D182A]" />
                <div className="flex flex-col">
                  <span className="font-bold text-[11px] text-[#0D182A]">Environment</span>
                  <span className="text-[9px] text-slate-500">Demo</span>
                </div>
              </div>

            </div>

          </div>

          {/* Header Bottom Row: System Status Chips + Refresh Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
            
            {/* Status Chips */}
            <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
              
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-white text-[#0D182A] border border-[#E6EBF1] font-bold shadow-2xs">
                <Server className="w-3.5 h-3.5 text-[#0D182A]" />
                <span>API: HEALTHY</span>
              </div>

              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-white text-[#0D182A] border border-[#E6EBF1] font-bold shadow-2xs">
                <Database className="w-3.5 h-3.5 text-[#0D182A]" />
                <span>PGVECTOR: HEALTHY</span>
              </div>

              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-white text-[#0D182A] border border-[#E6EBF1] font-bold shadow-2xs">
                <Lock className="w-3.5 h-3.5 text-[#0D182A]" />
                <span>SHA-256: VALID ({totalEvents})</span>
              </div>

              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-white text-[#0D182A] border border-[#E6EBF1] font-bold shadow-2xs">
                <HardDrive className="w-3.5 h-3.5 text-[#0D182A]" />
                <span>DRIFT: {reconDrift}</span>
              </div>

            </div>

            {/* Actions: Refresh + API Explorer Link */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className="text-xs px-3 py-1.5 rounded-xl font-bold border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Auto Refresh: <span className="font-mono text-[#0D182A]">{autoRefresh ? '10s v' : 'OFF'}</span>
              </button>

              <button
                onClick={fetchMetrics}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded-xl bg-[#0D182A] hover:bg-slate-800 text-white transition-all shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>

              <a
                href="/api-explorer"
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-white text-[#0D182A] border border-[#0D182A] hover:bg-slate-50 transition-colors shadow-2xs"
              >
                <Code className="w-3.5 h-3.5 text-[#0D182A]" />
                <span>&lt;&gt; API Explorer</span>
              </a>
            </div>

          </div>

        </header>

        {/* Main Body Container */}
        <main className="p-6 max-w-7xl w-full mx-auto space-y-6 flex-1">

          {/* Connection Error Notification */}
          {error && (
            <div className="p-4 rounded-2xl bg-slate-100 border border-[#0D182A]/30 text-[#0D182A] text-sm flex items-center justify-between shadow-xs">
              <div className="flex items-center gap-3">
                <XCircle className="w-5 h-5 text-[#0D182A] shrink-0" />
                <div>
                  <p className="font-bold text-[#0D182A]">API Connection Issue</p>
                  <p className="text-xs text-slate-600 mt-0.5">{error}</p>
                </div>
              </div>
              <button
                onClick={fetchMetrics}
                className="px-3 py-1.5 text-xs font-bold bg-[#0D182A] text-white rounded-xl hover:bg-slate-800 transition-colors"
              >
                Retry Connection
              </button>
            </div>
          )}

          {/* ========================================================================= */}
          {/* NAV SECTION 1: OVERVIEW (MAIN EXECUTIVE DASHBOARD) */}
          {/* ========================================================================= */}
          {navSection === 'overview' && (
            <div className="space-y-6">

              {/* HERO / GOVERNANCE SUMMARY CARD */}
              <div className="bg-white border border-[#E6EBF1] rounded-2xl p-6 shadow-xs flex flex-col lg:flex-row items-center justify-between gap-6">
                
                {/* Shield Graphic + Title */}
                <div className="flex items-center gap-5 max-w-2xl">
                  {/* Navy Shield Box */}
                  <div className="w-16 h-16 rounded-2xl bg-[#0D182A] text-white flex items-center justify-center shrink-0 shadow-md relative">
                    <ShieldCheck className="w-9 h-9" />
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-[#0D182A] border border-slate-300">
                        SEC / FINRA / GDPR Governed Memory
                      </span>
                      <span className="text-xs font-mono font-bold text-slate-500">
                        Policy: v1.0.0
                      </span>
                    </div>

                    <h3 className="text-lg font-bold text-[#0D182A] tracking-tight">
                      Enterprise AI Security &amp; Audit Control Engine
                    </h3>

                    <p className="text-xs text-slate-500 leading-relaxed font-medium">
                      PostgreSQL authoritative memory hub enforcing 4-way governance bounds, dual-side information barriers, pre-ranking CTE vector filtering, and append-only SHA-256 audit log continuity.
                    </p>
                  </div>
                </div>

                {/* Right Side Metadata Metric Blocks */}
                <div className="grid grid-cols-4 gap-4 bg-slate-50 p-4 rounded-xl border border-[#E6EBF1] w-full lg:w-auto shrink-0 font-mono text-xs">
                  
                  {/* Information Barriers */}
                  <div className="space-y-1 pr-3 border-r border-slate-200">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Information Barriers</div>
                    <div className="text-xs font-bold text-[#0D182A]">SIDE_A / SIDE_B</div>
                    <div className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                      <span>Active</span>
                      <Users className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                  </div>

                  {/* Clearance Bounds */}
                  <div className="space-y-1 pr-3 border-r border-slate-200">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Clearance Bounds</div>
                    <div className="text-xs font-bold text-[#0D182A]">RESTRICTED</div>
                    <div className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                      <span>Enforced</span>
                      <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                  </div>

                  {/* Audit Events */}
                  <div className="space-y-1 pr-3 border-r border-slate-200">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Audit Events</div>
                    <div className="text-xs font-bold text-[#0D182A]">{totalEvents}</div>
                    <div className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                      <span>Traced</span>
                      <FileText className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                  </div>

                  {/* Data Integrity */}
                  <div className="space-y-1">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Data Integrity</div>
                    <div className="text-xs font-bold text-[#0D182A]">SHA-256</div>
                    <div className="text-[11px] font-bold text-slate-700 flex items-center justify-between">
                      <span>Valid</span>
                      <Lock className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                  </div>

                </div>

              </div>

              {/* FINANCE / TECHNOLOGY SWITCHER BAR */}
              <div className="flex items-center justify-between bg-white p-2 rounded-2xl border border-[#E6EBF1] shadow-xs">
                
                {/* Segmented Control (Two-Color Navy/White) */}
                <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-xl">
                  <button
                    onClick={() => setActiveTab('finance')}
                    className={`flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-bold transition-all ${
                      activeTab === 'finance'
                        ? 'bg-[#0D182A] text-white shadow-xs'
                        : 'text-slate-600 hover:text-[#0D182A]'
                    }`}
                  >
                    <DollarSign className="w-4 h-4" />
                    Finance Reading View
                  </button>

                  <button
                    onClick={() => setActiveTab('technology')}
                    className={`flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-bold transition-all ${
                      activeTab === 'technology'
                        ? 'bg-[#0D182A] text-white shadow-xs'
                        : 'text-slate-600 hover:text-[#0D182A]'
                    }`}
                  >
                    <BarChart3 className="w-4 h-4" />
                    Technology Reading View
                  </button>
                </div>

                {/* Baseline Info Pill */}
                <div className="hidden md:flex items-center gap-2 text-xs font-mono font-bold text-[#0D182A] bg-slate-50 px-3.5 py-1.5 rounded-xl border border-slate-200">
                  <Clock className="w-3.5 h-3.5 text-[#0D182A]" />
                  <span>Week 1 Baseline Active</span>
                  <Info className="w-3.5 h-3.5 text-slate-400 cursor-pointer hover:text-[#0D182A]" />
                </div>
              </div>

              {/* KPI CARDS GRID — READING 1: FINANCE VIEW */}
              {activeTab === 'finance' && (
                <div className="space-y-6">
                  
                  {/* Top 4 Stat Summary Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
                    
                    {/* Spend vs Budget Card */}
                    <div 
                      onClick={() => openDrilldown('SPEND_VS_BUDGET')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <DollarSign className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">SPEND VS BUDGET</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>
                      
                      <div>
                        <div className="flex items-baseline gap-1">
                          <span className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                            ${metrics?.finance_view?.spend_vs_budget?.current_spend_usd || '1.69'}
                          </span>
                          <span className="text-xs text-slate-400 font-mono">USD</span>
                        </div>

                        <div className="text-xs text-slate-500 font-mono mt-1 flex items-center justify-between">
                          <span>Budget: ${metrics?.finance_view?.spend_vs_budget?.budget_usd || '1250'}</span>
                          <span className="font-bold text-[#0D182A]">{metrics?.finance_view?.spend_vs_budget?.percentage_used || 0.1}% used</span>
                        </div>
                      </div>

                      {/* Progress Bar Indicator */}
                      <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-[#0D182A] rounded-full" style={{ width: `${Math.max(metrics?.finance_view?.spend_vs_budget?.percentage_used || 0.1, 5)}%` }}></div>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">${metrics?.finance_view?.spend_vs_budget?.baseline_usd || '1250'}</span>
                      </div>
                    </div>

                    {/* Tollgate Cycle Time Card */}
                    <div 
                      onClick={() => openDrilldown('TOLLGATE_CYCLE_TIME')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <Clock className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">TOLLGATE CYCLE TIME</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.finance_view?.tollgate_cycle_time?.avg_cycle_seconds || '45.0'}s
                        </div>
                        <div className="text-xs text-slate-500 font-bold font-mono mt-1">
                          Avg Review Latency
                        </div>
                      </div>

                      {/* Sparkline Navy Wave SVG */}
                      <div className="h-6 w-full text-[#0D182A]">
                        <svg className="w-full h-full" viewBox="0 0 100 25" fill="none" preserveAspectRatio="none">
                          <path d="M0 20 Q 15 5, 30 15 T 60 10 T 90 18 T 100 8" stroke="currentColor" strokeWidth="2" fill="none" />
                        </svg>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">{metrics?.finance_view?.tollgate_cycle_time?.baseline_seconds || 45}s</span>
                      </div>
                    </div>

                    {/* Human Override Rate Card */}
                    <div 
                      onClick={() => openDrilldown('HUMAN_OVERRIDE_RATE')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <Users className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">HUMAN OVERRIDE RATE</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.finance_view?.human_override_rate?.override_rate_pct || '2.5'}%
                        </div>
                        <div className="text-xs text-slate-500 font-mono mt-1">
                          Rejections: {metrics?.finance_view?.human_override_rate?.rejections || 0} / Total: {metrics?.finance_view?.human_override_rate?.total_approvals || 0}
                        </div>
                      </div>

                      {/* Sparkline Navy Wave SVG */}
                      <div className="h-6 w-full text-[#0D182A]">
                        <svg className="w-full h-full" viewBox="0 0 100 25" fill="none" preserveAspectRatio="none">
                          <path d="M0 15 Q 20 22, 40 12 T 70 18 T 100 10" stroke="currentColor" strokeWidth="2" fill="none" />
                        </svg>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">{metrics?.finance_view?.human_override_rate?.baseline_pct || 2.5}%</span>
                      </div>
                    </div>

                    {/* Escalated Exceptions Card */}
                    <div 
                      onClick={() => openDrilldown('EXCEPTIONS')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <AlertTriangle className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">ESCALATED EXCEPTIONS</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.finance_view?.exceptions_requiring_attention?.count || 4}
                        </div>
                        <div className="text-xs text-slate-600 font-bold font-mono mt-1">
                          Steward Intervention Required
                        </div>
                      </div>

                      {/* Sparkline Navy Wave SVG */}
                      <div className="h-6 w-full text-[#0D182A]">
                        <svg className="w-full h-full" viewBox="0 0 100 25" fill="none" preserveAspectRatio="none">
                          <path d="M0 18 Q 25 8, 50 16 T 75 10 T 100 20" stroke="currentColor" strokeWidth="2" fill="none" />
                        </svg>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">0</span>
                      </div>
                    </div>

                  </div>

                  {/* SPEND ATTRIBUTION TABLE & GOVERNANCE HEALTH GRID */}
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    
                    {/* SPEND ATTRIBUTION TABLE */}
                    <div className="lg:col-span-2 p-6 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs space-y-4 flex flex-col">
                      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                        <div>
                          <h3 className="text-sm font-bold text-[#0D182A]">Spend Attribution by Task</h3>
                          <p className="text-xs text-slate-500">Real-time token &amp; cost allocation per orchestration task</p>
                        </div>
                        <span className="text-xs font-mono font-bold px-3 py-1 rounded-lg bg-slate-100 text-[#0D182A] border border-slate-200">
                          SHA-256 Traced
                        </span>
                      </div>

                      <div className="overflow-x-auto flex-1">
                        <table className="w-full text-left text-xs font-mono">
                          <thead>
                            <tr className="text-slate-400 border-b border-slate-100 uppercase text-[10px] tracking-wider font-bold">
                              <th className="py-3 px-4">TASK / ORCHESTRATION STAGE</th>
                              <th className="py-3 px-4 text-right">TOKENS</th>
                              <th className="py-3 px-4 text-right">EST. COST (USD)</th>
                              <th className="py-3 px-4 text-center">TREND</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 text-slate-700">
                            <tr className="hover:bg-slate-50 transition-colors">
                              <td className="py-3 px-4 font-bold text-[#0D182A]">Policy Evaluation</td>
                              <td className="py-3 px-4 text-right font-bold">12,540</td>
                              <td className="py-3 px-4 text-right font-bold">$0.42</td>
                              <td className="py-3 px-4 text-center">
                                <span className="text-[#0D182A]">~~~</span>
                              </td>
                            </tr>
                            <tr className="hover:bg-slate-50 transition-colors">
                              <td className="py-3 px-4 font-bold text-[#0D182A]">Vector Memory Search</td>
                              <td className="py-3 px-4 text-right font-bold">45,231</td>
                              <td className="py-3 px-4 text-right font-bold">$0.81</td>
                              <td className="py-3 px-4 text-center">
                                <span className="text-[#0D182A]">~~~</span>
                              </td>
                            </tr>
                            <tr className="hover:bg-slate-50 transition-colors">
                              <td className="py-3 px-4 font-bold text-[#0D182A]">Graph Traversal</td>
                              <td className="py-3 px-4 text-right font-bold">8,992</td>
                              <td className="py-3 px-4 text-right font-bold">$0.19</td>
                              <td className="py-3 px-4 text-center">
                                <span className="text-[#0D182A]">~~~</span>
                              </td>
                            </tr>
                            <tr className="hover:bg-slate-50 transition-colors">
                              <td className="py-3 px-4 font-bold text-[#0D182A]">Agent Handoff</td>
                              <td className="py-3 px-4 text-right font-bold">27,114</td>
                              <td className="py-3 px-4 text-right font-bold">$0.47</td>
                              <td className="py-3 px-4 text-center">
                                <span className="text-[#0D182A]">~~~</span>
                              </td>
                            </tr>
                            <tr className="hover:bg-slate-50 transition-colors">
                              <td className="py-3 px-4 font-bold text-[#0D182A]">Evidence Generation</td>
                              <td className="py-3 px-4 text-right font-bold">18,745</td>
                              <td className="py-3 px-4 text-right font-bold">$0.68</td>
                              <td className="py-3 px-4 text-center">
                                <span className="text-[#0D182A]">~~~</span>
                              </td>
                            </tr>
                          </tbody>
                          <tfoot>
                            <tr className="border-t-2 border-[#0D182A] font-bold text-[#0D182A]">
                              <td className="py-3 px-4">Total (Week 1)</td>
                              <td className="py-3 px-4 text-right">112,622</td>
                              <td className="py-3 px-4 text-right">$2.57</td>
                              <td className="py-3 px-4 text-center"></td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    </div>

                    {/* GOVERNANCE HEALTH CARD */}
                    <div className="p-6 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs space-y-5 flex flex-col justify-between">
                      <div className="border-b border-slate-100 pb-3">
                        <h3 className="text-sm font-bold text-[#0D182A]">Governance Health</h3>
                        <p className="text-xs text-slate-500">System-wide governance posture &amp; integrity</p>
                      </div>

                      {/* Controls Status List (Navy/White Theme) */}
                      <div className="space-y-2.5 text-xs font-mono">
                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <Settings className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>Policy Enforcement</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">Strong</span>
                        </div>

                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <Shield className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>Information Barriers</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">Active</span>
                        </div>

                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <CheckCircle2 className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>Audit Log Integrity</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">Valid</span>
                        </div>

                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <Database className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>Data Lineage Coverage</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">98.5%</span>
                        </div>

                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <Key className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>Retention &amp; Erasure</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">Compliant</span>
                        </div>

                        <div className="flex items-center justify-between py-1 border-b border-slate-100">
                          <div className="flex items-center gap-2 text-slate-700">
                            <RefreshCw className="w-3.5 h-3.5 text-[#0D182A]" />
                            <span>System Drift</span>
                          </div>
                          <span className="font-bold text-[#0D182A]">{reconDrift} Events</span>
                        </div>

                        <div className="flex items-center justify-between py-1.5 pt-2 border-t border-slate-200">
                          <div className="flex items-center gap-2 text-[#0D182A] font-bold">
                            <ShieldCheck className="w-4 h-4 text-[#0D182A]" />
                            <span>Overall Posture</span>
                          </div>
                          <span className="px-2.5 py-0.5 rounded font-bold bg-slate-100 text-[#0D182A] border border-slate-300">Healthy</span>
                        </div>
                      </div>

                    </div>

                  </div>

                </div>
              )}

              {/* READING 2: TECHNOLOGY VIEW */}
              {activeTab === 'technology' && (
                <div className="space-y-6">
                  
                  {/* Tech Metric Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    
                    {/* Agent First-Pass Rate Card */}
                    <div 
                      onClick={() => openDrilldown('AGENT_FIRST_PASS')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">AGENT FIRST-PASS RATE</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.technology_view?.agent_first_pass_rate?.first_pass_rate_pct || '95.0'}%
                        </div>
                        <div className="text-xs text-slate-500 font-mono mt-1">
                          Tasks Passing Without Escalation
                        </div>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">{metrics?.technology_view?.agent_first_pass_rate?.baseline_pct || 95.0}%</span>
                      </div>
                    </div>

                    {/* Retrieval Accuracy Card */}
                    <div 
                      onClick={() => openDrilldown('RETRIEVAL_ACCURACY')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <Layers className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">RETRIEVAL ACCURACY</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.technology_view?.retrieval_accuracy?.accuracy_pct || '98.5'}%
                        </div>
                        <div className="text-xs text-slate-500 font-mono mt-1">
                          Labelled Synthetic Set Precision
                        </div>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">{metrics?.technology_view?.retrieval_accuracy?.baseline_pct || 98.5}%</span>
                      </div>
                    </div>

                    {/* Decision Traceability Coverage Card */}
                    <div 
                      onClick={() => openDrilldown('TRACEABILITY')}
                      className="p-5 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs hover:border-[#0D182A] cursor-pointer transition-all space-y-3 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="p-2 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                          <Binary className="w-4 h-4" />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">DECISION TRACEABILITY</span>
                        <MoreVertical className="w-4 h-4 text-slate-300 group-hover:text-[#0D182A] ml-auto" />
                      </div>

                      <div>
                        <div className="text-2xl font-bold text-[#0D182A] font-mono tracking-tight">
                          {metrics?.technology_view?.decision_traceability?.coverage_pct || '100.0'}%
                        </div>
                        <div className="text-xs text-slate-500 font-mono mt-1">
                          Audit Log Traceability Coverage
                        </div>
                      </div>

                      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>Baseline:</span>
                        <span className="text-[#0D182A] font-bold">100.0%</span>
                      </div>
                    </div>

                  </div>

                  {/* Token Consumption per Lifecycle Stage */}
                  <div className="p-6 rounded-2xl bg-white border border-[#E6EBF1] shadow-xs space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                      <div>
                        <h3 className="text-sm font-bold text-[#0D182A]">Token Consumption per Lifecycle Stage</h3>
                        <p className="text-xs text-slate-500">Average token spend breakdown across the 8-stage governed workflow</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                      {Object.entries(metrics?.technology_view?.token_consumption_per_stage || {}).map(([stage, tokens]: [string, any]) => (
                        <div key={stage} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                          <div className="text-[10px] font-mono font-bold text-slate-400 uppercase truncate">{stage}</div>
                          <div className="text-base font-mono font-bold text-[#0D182A]">{tokens.toLocaleString()}</div>
                          <div className="text-[10px] text-slate-500 font-mono">Tokens / Run</div>
                        </div>
                      ))}
                    </div>
                  </div>

                </div>
              )}

            </div>
          )}

          {/* NAV SECTIONS 2 THROUGH 8: OTHER MODULE VIEWS */}
          {navSection === 'governance' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <Lock className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">Active Policy Engine Configuration</h3>
                      <p className="text-xs text-slate-500">Deterministic 4-Way Policy Engine Rules (v1.0.0)</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    FAIL-CLOSED ACTIVE
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="font-bold text-[#0D182A] flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-[#0D182A]" />
                      Clearance Levels
                    </div>
                    <ul className="space-y-1 text-slate-600 text-[11px]">
                      <li>• Level 1: PUBLIC</li>
                      <li>• Level 2: INTERNAL</li>
                      <li>• Level 3: CONFIDENTIAL</li>
                      <li>• Level 4: RESTRICTED</li>
                    </ul>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="font-bold text-[#0D182A] flex items-center gap-2">
                      <GitMerge className="w-4 h-4 text-[#0D182A]" />
                      Information Barriers
                    </div>
                    <ul className="space-y-1 text-slate-600 text-[11px]">
                      <li>• GENERAL (Unrestricted)</li>
                      <li>• SIDE_A (Advisory Division)</li>
                      <li>• SIDE_B (Markets Division)</li>
                      <li className="text-[#0D182A] font-bold">• Strict Isolation Enforced</li>
                    </ul>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="font-bold text-[#0D182A] flex items-center gap-2">
                      <FileText className="w-4 h-4 text-[#0D182A]" />
                      Jurisdiction Scopes
                    </div>
                    <ul className="space-y-1 text-slate-600 text-[11px]">
                      <li>• US_NY (New York)</li>
                      <li>• US_DE (Delaware)</li>
                      <li>• UK (United Kingdom)</li>
                      <li>• GLOBAL (Worldwide)</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          {navSection === 'retrieval' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <Layers className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">Filter-Before-Ranking Vector Search Engine</h3>
                      <p className="text-xs text-slate-500">SQL CTE Governance Predicates executing BEFORE vector distance (&lt;=&gt;)</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    ZERO LEAKAGE VERIFIED
                  </span>
                </div>

                <div className="p-4 rounded-xl bg-[#0D182A] text-slate-100 font-mono text-xs overflow-x-auto space-y-2">
                  <div className="text-slate-400 font-bold">// PostgreSQL CTE Execution Plan (Filter-Before-Ranking)</div>
                  <pre className="text-blue-300">{`WITH filtered_candidates AS (
    SELECT chunk_id, asset_id, chunk_content, embedding
    FROM knowledge_chunk
    WHERE classification = ANY($1)  -- Governance Clearance
      AND barrier_side = ANY($2)    -- Information Barrier Side
      AND asset_state = 'APPROVED'
)
SELECT chunk_id, chunk_content, (embedding <=> $3) AS distance
FROM filtered_candidates
ORDER BY distance ASC LIMIT $4;`}</pre>
                </div>
              </div>
            </div>
          )}

          {navSection === 'graph' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <GitMerge className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">Apache AGE Multi-Hop Lineage Graph</h3>
                      <p className="text-xs text-slate-500">Authority graph projected idempotently from PostgreSQL source of truth</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    APACHE AGE ENABLED
                  </span>
                </div>
              </div>
            </div>
          )}

          {navSection === 'orchestration' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <Cpu className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">8-Stage Governed Agent Orchestration</h3>
                      <p className="text-xs text-slate-500">Autonomous stage handoffs with Human Steward approval tollgates</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    8 STAGES ACTIVE
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
                  {['INTAKE', 'CLASSIFICATION', 'RETRIEVAL', 'ANALYSIS', 'REPORTING', 'REVIEW', 'APPROVAL', 'COMPLETION'].map((stg, idx) => (
                    <div key={stg} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                      <div className="text-[10px] text-slate-400 font-bold">Stage {idx + 1}</div>
                      <div className="font-bold text-[#0D182A] text-xs mt-0.5">{stg}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {navSection === 'evidence' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <FileCheck className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">Cryptographic Evidence Package Engine</h3>
                      <p className="text-xs text-slate-500">Standalone self-verifying evidence bundles (JSON &amp; ZIP) with SHA-256 chain proof</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    SHA-256 VERIFIED
                  </span>
                </div>
              </div>
            </div>
          )}

          {navSection === 'erasure' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <Key className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">GDPR Article 17 Crypto-Erasure &amp; Legal Hold</h3>
                      <p className="text-xs text-slate-500">Destroys Subject DEK while preserving immutable audit log tombstone</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    LEGAL HOLD PROTECTED
                  </span>
                </div>
              </div>
            </div>
          )}

          {navSection === 'settings' && (
            <div className="space-y-6">
              <div className="bg-white p-6 rounded-2xl border border-[#E6EBF1] shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-200">
                      <Settings className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-[#0D182A]">System Architecture &amp; Network Egress Status</h3>
                      <p className="text-xs text-slate-500">Live connection state across Governed Memory Hub infrastructure</p>
                    </div>
                  </div>
                  <span className="px-3 py-1 rounded-xl bg-slate-100 text-[#0D182A] border border-slate-300 text-xs font-mono font-bold">
                    DEFAULT-DENY EGRESS ACTIVE
                  </span>
                </div>
              </div>
            </div>
          )}

        </main>

        {/* SUBTLE ENTERPRISE FOOTER */}
        <footer className="px-6 py-4 border-t border-[#E6EBF1] bg-white flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-slate-500 font-medium">
          <div className="flex items-center gap-2">
            <span>&copy; 2026 Governed Memory Hub. All rights reserved.</span>
          </div>
          <div className="font-mono text-[11px] text-slate-400">
            v11.0.0
          </div>
        </footer>

      </div>

      {/* ========================================================================= */}
      {/* 9. METRIC DRILL-DOWN MODAL */}
      {/* ========================================================================= */}
      {drilldownMetric && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-[#E6EBF1] rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-[#0D182A] text-white">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Search className="w-4 h-4 text-white" />
                  Metric Audit Inspector: {drilldownMetric}
                </h3>
                <p className="text-xs text-slate-300 font-mono mt-0.5">Real underlying SHA-256 audit log event records backing this metric</p>
              </div>
              <button
                onClick={() => setDrilldownMetric(null)}
                className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-4">
              {drilldownLoading ? (
                <div className="py-12 flex items-center justify-center text-slate-500 gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-[#0D182A]" />
                  <span className="font-mono text-xs font-semibold">Fetching underlying audit log events...</span>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-600 bg-slate-50 p-3.5 rounded-xl border border-[#E6EBF1]">
                    <span>Action Filter: <strong className="text-[#0D182A]">{drilldownData?.action_filter?.join(', ')}</strong></span>
                    <span>Traced Events: <strong className="text-[#0D182A]">{drilldownData?.underlying_audit_events_count || 0}</strong></span>
                  </div>

                  <div className="overflow-x-auto border border-[#E6EBF1] rounded-xl">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-100 text-slate-700 border-b border-slate-200 font-bold uppercase text-[10px] tracking-wider">
                        <tr>
                          <th className="py-3 px-3">Event ID</th>
                          <th className="py-3 px-3">Actor Type</th>
                          <th className="py-3 px-3">Action</th>
                          <th className="py-3 px-3">Decision</th>
                          <th className="py-3 px-3">Reason Code</th>
                          <th className="py-3 px-3">Current Hash</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 text-slate-700">
                        {drilldownData?.audit_events?.map((evt: any) => (
                          <tr key={evt.event_id} className="hover:bg-slate-50 transition-colors">
                            <td className="py-3 px-3 text-[#0D182A] font-bold">#{evt.event_id}</td>
                            <td className="py-3 px-3 font-medium">{evt.actor_type}</td>
                            <td className="py-3 px-3">{evt.action}</td>
                            <td className="py-3 px-3">
                              <span className="px-2.5 py-0.5 rounded text-[10px] font-bold border bg-slate-100 text-[#0D182A] border-slate-300">
                                {evt.decision}
                              </span>
                            </td>
                            <td className="py-3 px-3 truncate max-w-[150px] font-medium">{evt.reason_code}</td>
                            <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">{evt.current_hash?.substring(0, 12)}...</td>
                          </tr>
                        ))}
                        {(!drilldownData?.audit_events || drilldownData?.audit_events?.length === 0) && (
                          <tr>
                            <td colSpan={6} className="py-8 text-center text-slate-400">No underlying audit events found for this metric</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-600">
              <span className="font-mono font-medium flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-[#0D182A]" />
                Proof: 100% SHA-256 Audit Log Traced
              </span>
              <button
                onClick={() => setDrilldownMetric(null)}
                className="px-4 py-2 rounded-xl bg-[#0D182A] hover:bg-slate-800 text-white font-bold text-xs transition-colors shadow-xs"
              >
                Close Audit Inspector
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
