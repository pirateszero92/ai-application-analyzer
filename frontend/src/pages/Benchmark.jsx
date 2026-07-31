import React, { useState, useEffect, useRef } from 'react';
import { 
  Zap, 
  Play, 
  Square, 
  Database, 
  Globe, 
  Users, 
  Clock, 
  Activity, 
  CheckCircle, 
  AlertTriangle, 
  Trash2, 
  Eye, 
  X, 
  RefreshCw,
  Cpu,
  BarChart2
} from 'lucide-react';

const parseBoldText = (text) => {
  if (!text) return '';
  const parts = text.split(/\*\*(.*?)\*\*/g);
  return parts.map((part, i) => {
    if (i % 2 === 1) return <strong key={i} style={{ color: 'white', fontWeight: 700 }}>{part}</strong>;
    return part;
  });
};

const renderMarkdown = (text) => {
  if (!text) return <p style={{ color: 'var(--text-muted)' }}>ไม่มีข้อมูลผลวิเคราะห์จาก AI</p>;
  const lines = text.split('\n');
  return lines.map((line, idx) => {
    if (line.startsWith('### ')) {
      return <h4 key={idx} style={{ color: 'var(--color-primary)', marginTop: '18px', marginBottom: '8px', fontSize: '1.1rem' }}>{line.slice(4)}</h4>;
    }
    if (line.startsWith('## ')) {
      return <h3 key={idx} style={{ color: 'var(--color-primary)', marginTop: '22px', marginBottom: '10px', fontSize: '1.25rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '6px' }}>{line.slice(3)}</h3>;
    }
    if (line.startsWith('# ')) {
      return <h2 key={idx} style={{ color: 'white', marginTop: '26px', marginBottom: '14px', fontSize: '1.5rem' }}>{line.slice(2)}</h2>;
    }
    if (line.startsWith('* ') || line.startsWith('- ')) {
      const content = line.slice(2);
      return (
        <li key={idx} style={{ marginLeft: '20px', marginBottom: '6px', color: 'var(--text-primary)', listStyleType: 'square' }}>
          {parseBoldText(content)}
        </li>
      );
    }
    if (line.trim() === '') {
      return <div key={idx} style={{ height: '8px' }} />;
    }
    return <p key={idx} style={{ marginBottom: '8px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>{parseBoldText(line)}</p>;
  });
};

export default function Benchmark({ token, API_BASE }) {
  const [mode, setMode] = useState('http'); // 'http' or 'postgres'
  
  // Default form state
  const [name, setName] = useState('PostgreSQL System Catalog & Ping Test');
  const [targetUrl, setTargetUrl] = useState('http://localhost:8000/api/health/live');
  const [httpMethod, setHttpMethod] = useState('GET');
  const [headersJson, setHeadersJson] = useState('{\n  "Content-Type": "application/json"\n}');
  const [payloadJson, setPayloadJson] = useState('{\n  "test": true\n}');

  // Postgres form state
  const [dbLabel, setDbLabel] = useState('WMS-DB');
  const [sqlQuery, setSqlQuery] = useState('SELECT count(*), max(pid) FROM pg_stat_activity;');

  // Common form state
  const [concurrentUsers, setConcurrentUsers] = useState(20);
  const [durationSeconds, setDurationSeconds] = useState(15);

  // Live status state
  const [liveStatus, setLiveStatus] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Historical reports
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [loadingReports, setLoadingReports] = useState(false);

  // Settings db connections list
  const [availableDbs, setAvailableDbs] = useState(['WMS-DB', 'TMS-DB']);

  // Fetch settings to populate available DB connections
  useEffect(() => {
    fetch(`${API_BASE}/api/settings`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.db_connections && data.db_connections.length > 0) {
          const labels = data.db_connections.map(c => c.label || c.host);
          setAvailableDbs(labels);
          if (labels[0]) setDbLabel(labels[0]);
        }
      })
      .catch(err => console.error("Error loading settings DB connections:", err));
  }, [token, API_BASE]);

  // Polling live status
  useEffect(() => {
    let interval = null;
    const fetchLive = () => {
      fetch(`${API_BASE}/api/benchmark/live`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => res.json())
        .then(data => {
          setLiveStatus(data);
          if (data.is_running) {
            // refresh reports list when test completes
          }
        })
        .catch(err => console.error("Error fetching live status:", err));
    };

    fetchLive();
    interval = setInterval(fetchLive, 1000);
    return () => clearInterval(interval);
  }, [token, API_BASE]);

  // Fetch reports history
  const fetchReports = () => {
    setLoadingReports(true);
    fetch(`${API_BASE}/api/benchmark/reports`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        setReports(Array.isArray(data) ? data : []);
        setLoadingReports(false);
      })
      .catch(err => {
        console.error("Error fetching reports:", err);
        setLoadingReports(false);
      });
  };

  useEffect(() => {
    fetchReports();
  }, [token, API_BASE]);

  // Refresh reports when a benchmark finishes
  const prevRunningRef = useRef(false);
  useEffect(() => {
    if (prevRunningRef.current && liveStatus && !liveStatus.is_running) {
      fetchReports();
    }
    prevRunningRef.current = liveStatus?.is_running || false;
  }, [liveStatus]);

  // Handlers
  const handleStartBenchmark = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg('');

    const body = {
      name: name || (mode === 'http' ? 'HTTP Benchmark' : 'PostgreSQL Benchmark'),
      mode,
      target_url: targetUrl,
      http_method: httpMethod,
      headers_json: headersJson,
      payload_json: payloadJson,
      db_label: dbLabel,
      sql_query: sqlQuery,
      concurrent_users: parseInt(concurrentUsers),
      duration_seconds: parseInt(durationSeconds)
    };

    fetch(`${API_BASE}/api/benchmark/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(body)
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || 'Failed to start benchmark');
        }
        return res.json();
      })
      .then(() => {
        setIsSubmitting(false);
      })
      .catch(err => {
        setErrorMsg(err.message);
        setIsSubmitting(false);
      });
  };

  const handleStopBenchmark = () => {
    fetch(`${API_BASE}/api/benchmark/stop`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .catch(err => console.error("Error stopping benchmark:", err));
  };

  const handleDeleteReport = (id, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete benchmark report #${id}?`)) return;

    fetch(`${API_BASE}/api/benchmark/reports/${id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(() => {
        setReports(reports.filter(r => r.id !== id));
        if (selectedReport?.id === id) setSelectedReport(null);
      })
      .catch(err => console.error("Error deleting report:", err));
  };

  // Preset shortcuts
  const applyPresetQuery = (type) => {
    if (type === 'stat_activity') {
      setName('PostgreSQL Active Session Load Test');
      setSqlQuery('SELECT count(*), max(pid) FROM pg_stat_activity;');
    } else if (type === 'stat_db') {
      setName('PostgreSQL DB Stats Benchmark');
      setSqlQuery('SELECT datname, numbackends FROM pg_stat_database LIMIT 10;');
    } else if (type === 'raw_ping') {
      setName('PostgreSQL Raw Connection Ping');
      setSqlQuery('SELECT pg_backend_pid(), current_timestamp;');
    }
  };

  const isRunning = liveStatus?.is_running;

  return (
    <div className="fade-in" style={{ paddingBottom: '50px' }}>
      
      {/* PAGE TITLE & MODE SWITCHER */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '24px',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <h2 style={{ fontSize: '1.6rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Zap style={{ color: 'var(--color-primary)' }} size={28} />
            <span>Benchmark Test Suite</span>
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '4px' }}>
            Real-time Load Testing for HTTP APIs & PostgreSQL Queries with AI Performance Analysis
          </p>
        </div>

        {/* Mode Selector Tabs */}
        <div className="glass-card" style={{ display: 'flex', padding: '4px', gap: '4px', borderRadius: '12px' }}>
          <button
            onClick={() => { setMode('http'); setName('HTTP API Stress Test'); }}
            style={{
              padding: '8px 18px',
              borderRadius: '8px',
              border: 'none',
              background: mode === 'http' ? 'var(--color-primary)' : 'transparent',
              color: mode === 'http' ? 'white' : 'var(--text-secondary)',
              fontWeight: mode === 'http' ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s'
            }}
          >
            <Globe size={16} />
            <span>HTTP API</span>
          </button>
          <button
            onClick={() => { setMode('postgres'); setName('PostgreSQL Query Load Test'); }}
            style={{
              padding: '8px 18px',
              borderRadius: '8px',
              border: 'none',
              background: mode === 'postgres' ? 'var(--color-primary)' : 'transparent',
              color: mode === 'postgres' ? 'white' : 'var(--text-secondary)',
              fontWeight: mode === 'postgres' ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s'
            }}
          >
            <Database size={16} />
            <span>PostgreSQL DB</span>
          </button>
        </div>
      </div>

      {/* ERROR BANNER */}
      {errorMsg && (
        <div className="glass-card" style={{
          background: 'rgba(244, 63, 94, 0.1)',
          borderColor: 'rgba(244, 63, 94, 0.3)',
          color: 'var(--color-danger)',
          padding: '12px 16px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <AlertTriangle size={18} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* REAL-TIME RUNNING DASHBOARD (If benchmark is currently executing) */}
      {isRunning && liveStatus && (
        <div className="glass-card fade-in" style={{
          background: 'linear-gradient(135deg, rgba(6,182,212,0.1) 0%, rgba(99,102,241,0.1) 100%)',
          borderColor: 'var(--color-primary)',
          padding: '24px',
          marginBottom: '30px',
          borderRadius: '16px',
          boxShadow: '0 8px 32px rgba(6, 182, 212, 0.15)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'var(--color-danger)',
                boxShadow: '0 0 12px var(--color-danger)',
                animation: 'pulse 1.5s infinite'
              }} />
              <h3 style={{ fontSize: '1.2rem', margin: 0, fontWeight: 700 }}>
                BENCHMARK IN PROGRESS: {liveStatus.name}
              </h3>
            </div>

            <button
              onClick={handleStopBenchmark}
              className="btn-danger"
              style={{ padding: '8px 16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Square size={14} /> Stop Benchmark
            </button>
          </div>

          <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Target: <code>{liveStatus.target_summary}</code> | Mode: <strong>{liveStatus.mode?.toUpperCase()}</strong>
          </div>

          {/* Progress Bar */}
          <div style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px' }}>
              <span>Elapsed: <strong>{liveStatus.elapsed_seconds}s</strong> / {liveStatus.duration_seconds}s</span>
              <span>Remaining: <strong>{liveStatus.remaining_seconds}s</strong> ({liveStatus.progress_pct}%)</span>
            </div>
            <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${liveStatus.progress_pct}%`,
                background: 'linear-gradient(90deg, var(--color-primary), var(--color-secondary))',
                transition: 'width 0.5s ease'
              }} />
            </div>
          </div>

          {/* Live Metric Cards Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: '12px'
          }}>
            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>SIMULATED USERS</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-primary)' }}>
                {liveStatus.concurrent_users}
              </div>
            </div>

            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>TOTAL OPERATIONS</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                {liveStatus.total_operations?.toLocaleString()}
              </div>
            </div>

            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>THROUGHPUT (RPS/QPS)</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#34d399' }}>
                {liveStatus.current_ops_per_sec} <span style={{ fontSize: '0.75rem' }}>ops/s</span>
              </div>
            </div>

            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>AVG LATENCY</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#fbbf24' }}>
                {liveStatus.current_avg_ms} <span style={{ fontSize: '0.75rem' }}>ms</span>
              </div>
            </div>

            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>P99 LATENCY</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f87171' }}>
                {liveStatus.current_p99_ms} <span style={{ fontSize: '0.75rem' }}>ms</span>
              </div>
            </div>

            <div className="glass-card" style={{ padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>ERROR RATE</div>
              <div style={{
                fontSize: '1.4rem',
                fontWeight: 700,
                color: liveStatus.current_error_rate > 0 ? 'var(--color-danger)' : 'var(--text-muted)'
              }}>
                {liveStatus.current_error_rate}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* BENCHMARK CONFIGURATION FORM CARD */}
      <div className="glass-card" style={{ padding: '24px', marginBottom: '30px', borderRadius: '16px' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          {mode === 'http' ? <Globe size={20} style={{ color: 'var(--color-primary)' }} /> : <Database size={20} style={{ color: 'var(--color-primary)' }} />}
          <span>{mode === 'http' ? 'HTTP API Load Test Configuration' : 'PostgreSQL Direct DB Benchmark Configuration'}</span>
        </h3>

        <form onSubmit={handleStartBenchmark}>
          {/* Test Name & Common Parameters */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            <div className="form-group">
              <label>Test Name</label>
              <input
                type="text"
                className="form-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Custom benchmark name..."
                required
              />
            </div>

            {/* SIMULATED CONCURRENT USERS INPUT */}
            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Users size={14} style={{ color: 'var(--color-primary)' }} />
                  Simulated Concurrent Users
                </span>
                <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>{concurrentUsers} Users</span>
              </label>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <input
                  type="range"
                  min="1"
                  max={mode === 'http' ? "500" : "200"}
                  value={concurrentUsers}
                  onChange={(e) => setConcurrentUsers(parseInt(e.target.value) || 1)}
                  style={{ flex: 1, accentColor: 'var(--color-primary)' }}
                />
                <input
                  type="number"
                  className="form-input"
                  style={{ width: '80px', textAlign: 'center' }}
                  min="1"
                  max={mode === 'http' ? "500" : "200"}
                  value={concurrentUsers}
                  onChange={(e) => setConcurrentUsers(parseInt(e.target.value) || 1)}
                />
              </div>
            </div>

            {/* TEST DURATION INPUT */}
            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={14} style={{ color: 'var(--color-primary)' }} />
                  Test Duration (Seconds)
                </span>
                <span style={{ fontWeight: 700 }}>{durationSeconds}s</span>
              </label>
              <input
                type="number"
                className="form-input"
                min="5"
                max="300"
                value={durationSeconds}
                onChange={(e) => setDurationSeconds(parseInt(e.target.value) || 5)}
              />
            </div>
          </div>

          {/* MODE SPECIFIC FIELDS */}
          {mode === 'http' ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '12px', marginBottom: '16px' }}>
                <div className="form-group">
                  <label>Method</label>
                  <select
                    className="form-input"
                    value={httpMethod}
                    onChange={(e) => setHttpMethod(e.target.value)}
                  >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Target Endpoint URL</label>
                  <input
                    type="url"
                    className="form-input"
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    placeholder="http://tms-service:8080/api/..."
                    required
                  />
                </div>
              </div>

              {/* Advanced Headers / Payload JSON */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '20px' }}>
                <div className="form-group">
                  <label>Headers (JSON)</label>
                  <textarea
                    className="form-input"
                    rows="3"
                    style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                    value={headersJson}
                    onChange={(e) => setHeadersJson(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Body Payload (JSON, for POST/PUT)</label>
                  <textarea
                    className="form-input"
                    rows="3"
                    style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                    value={payloadJson}
                    onChange={(e) => setPayloadJson(e.target.value)}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '16px', marginBottom: '16px' }}>
                <div className="form-group">
                  <label>Target Database Connection</label>
                  <select
                    className="form-input"
                    value={dbLabel}
                    onChange={(e) => setDbLabel(e.target.value)}
                  >
                    {availableDbs.map((label, idx) => (
                      <option key={idx} value={label}>{label}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>SQL Benchmark Query</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Preset Shortcuts:</span>
                  </label>
                  
                  {/* Preset Shortcuts Buttons */}
                  <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                      onClick={() => applyPresetQuery('stat_activity')}
                    >
                      📊 Active Sessions Query
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                      onClick={() => applyPresetQuery('stat_db')}
                    >
                      💾 DB Stats Query
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                      onClick={() => applyPresetQuery('raw_ping')}
                    >
                      ⚡ Raw Connection Ping
                    </button>
                  </div>
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '20px' }}>
                <textarea
                  className="form-input"
                  rows="4"
                  style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                  value={sqlQuery}
                  onChange={(e) => setSqlQuery(e.target.value)}
                  placeholder="SELECT * FROM table WHERE ..."
                  required
                />
              </div>
            </div>
          )}

          {/* Submit Action */}
          <button
            type="submit"
            className="btn-primary"
            disabled={isRunning || isSubmitting}
            style={{
              padding: '12px 24px',
              fontSize: '1rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 16px rgba(6,182,212,0.3)'
            }}
          >
            {isRunning ? (
              <>
                <RefreshCw className="spin" size={18} />
                <span>Benchmark Running...</span>
              </>
            ) : (
              <>
                <Play size={18} />
                <span>Start Benchmark Load Test</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* HISTORICAL BENCHMARK REPORTS ARCHIVE */}
      <div className="glass-card" style={{ padding: '24px', borderRadius: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <h3 style={{ fontSize: '1.1rem', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart2 size={20} style={{ color: 'var(--color-primary)' }} />
            <span>Benchmark Reports History</span>
          </h3>
          <button
            className="btn-secondary"
            onClick={fetchReports}
            style={{ padding: '6px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={14} className={loadingReports ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>

        {reports.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
            No benchmark runs recorded yet. Start a new test above!
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '12px' }}>ID</th>
                  <th style={{ padding: '12px' }}>Date / Time</th>
                  <th style={{ padding: '12px' }}>Name</th>
                  <th style={{ padding: '12px' }}>Mode</th>
                  <th style={{ padding: '12px' }}>Target Summary</th>
                  <th style={{ padding: '12px' }}>Simulated Users</th>
                  <th style={{ padding: '12px' }}>RPS / QPS</th>
                  <th style={{ padding: '12px' }}>Avg Latency</th>
                  <th style={{ padding: '12px' }}>p99 Latency</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr
                    key={r.id}
                    style={{
                      borderBottom: '1px solid rgba(255,255,255,0.05)',
                      transition: 'background 0.2s',
                      cursor: 'pointer'
                    }}
                    onClick={() => setSelectedReport(r)}
                    className="table-row-hover"
                  >
                    <td style={{ padding: '12px', fontWeight: 600 }}>#{r.id}</td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      {new Date(r.timestamp).toLocaleString('th-TH')}
                    </td>
                    <td style={{ padding: '12px', fontWeight: 600 }}>{r.name}</td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: r.mode === 'http' ? 'rgba(6,182,212,0.15)' : 'rgba(99,102,241,0.15)',
                        color: r.mode === 'http' ? 'var(--color-primary)' : 'var(--color-secondary)'
                      }}>
                        {r.mode.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '12px', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {r.target_summary}
                    </td>
                    <td style={{ padding: '12px', fontWeight: 600 }}>
                      {r.concurrent_users} users
                    </td>
                    <td style={{ padding: '12px', fontWeight: 700, color: '#34d399' }}>
                      {r.ops_per_sec} ops/s
                    </td>
                    <td style={{ padding: '12px' }}>
                      {r.avg_latency_ms} ms
                    </td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        color: r.p99_ms > 1000 ? 'var(--color-danger)' : r.p99_ms > 200 ? '#fbbf24' : '#34d399',
                        fontWeight: 700
                      }}>
                        {r.p99_ms} ms
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                        <button
                          className="btn-secondary"
                          style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                          onClick={(e) => { e.stopPropagation(); setSelectedReport(r); }}
                        >
                          <Eye size={14} /> View
                        </button>
                        <button
                          className="btn-danger"
                          style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                          onClick={(e) => handleDeleteReport(r.id, e)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* REPORT DETAIL MODAL */}
      {selectedReport && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.75)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px'
        }}>
          <div className="glass-card fade-in" style={{
            width: '100%',
            maxWidth: '900px',
            maxHeight: '90vh',
            overflowY: 'auto',
            borderRadius: '20px',
            padding: '30px',
            position: 'relative'
          }}>
            {/* Close Button */}
            <button
              onClick={() => setSelectedReport(null)}
              style={{
                position: 'absolute',
                top: '20px', right: '20px',
                background: 'rgba(255,255,255,0.1)',
                border: 'none',
                color: 'white',
                width: '32px', height: '32px',
                borderRadius: '50%',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}
            >
              <X size={18} />
            </button>

            {/* Modal Header */}
            <h3 style={{ fontSize: '1.4rem', marginBottom: '8px', paddingRight: '40px' }}>
              Benchmark Report #{selectedReport.id}: {selectedReport.name}
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '20px' }}>
              Executed on {new Date(selectedReport.timestamp).toLocaleString('th-TH')} | Target: <code>{selectedReport.target_summary}</code>
            </p>

            {/* Metrics Breakdown Grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
              gap: '12px',
              marginBottom: '24px'
            }}>
              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>SIMULATED USERS</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--color-primary)' }}>
                  {selectedReport.concurrent_users} users
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>THROUGHPUT</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#34d399' }}>
                  {selectedReport.ops_per_sec} ops/s
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>TOTAL OPERATIONS</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>
                  {selectedReport.total_operations}
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>AVG LATENCY</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fbbf24' }}>
                  {selectedReport.avg_latency_ms} ms
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>P50 (MEDIAN)</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>
                  {selectedReport.p50_ms} ms
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>P90</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>
                  {selectedReport.p90_ms} ms
                </div>
              </div>

              <div className="glass-card" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>P99 (WORST 1%)</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f87171' }}>
                  {selectedReport.p99_ms} ms
                </div>
              </div>
            </div>

            {/* AI Performance Optimization Analysis */}
            <div className="glass-card" style={{
              padding: '20px',
              borderRadius: '14px',
              background: 'rgba(99, 102, 241, 0.08)',
              borderColor: 'rgba(99, 102, 241, 0.3)'
            }}>
              <h4 style={{ fontSize: '1.05rem', color: 'var(--color-secondary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🤖 AI Performance Optimization Recommendation
              </h4>
              <div className="markdown-content" style={{ fontSize: '0.9rem', lineHeight: '1.6' }}>
                {selectedReport.ai_recommendation ? (
                  renderMarkdown(selectedReport.ai_recommendation)
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>No AI analysis generated.</span>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
