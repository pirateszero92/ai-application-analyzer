import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  Lock, 
  AlertTriangle, 
  CheckCircle2, 
  XCircle, 
  RefreshCw, 
  Server, 
  Database, 
  Cpu, 
  HardDrive, 
  Terminal, 
  Zap, 
  Play, 
  Square, 
  Flame, 
  Clock, 
  Radio, 
  Bot, 
  ChevronRight, 
  AlertOctagon, 
  HelpCircle, 
  Copy, 
  Check,
  Maximize2,
  Minimize2,
  Move,
  X
} from 'lucide-react';

export default function RealtimeDBMonitor({ token, API_BASE }) {
  const [liveData, setLiveData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedDb, setSelectedDb] = useState('ALL');
  const [terminatingPid, setTerminatingPid] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiModalData, setAiModalData] = useState(null);
  const [copySuccess, setCopySuccess] = useState(false);
  const [activeTab, setActiveTab] = useState('locks'); // 'locks' | 'queries' | 'wait_events' | 'pgbouncer'

  // Draggable & Resizable Modal State
  const [modalPos, setModalPos] = useState({ x: 80, y: 50 });
  const [modalSize, setModalSize] = useState({ width: 850, height: 600 });
  const [isMaximized, setIsMaximized] = useState(false);
  
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, modalX: 0, modalY: 0 });

  const isResizingRef = useRef(false);
  const resizeStartRef = useRef({ mouseX: 0, mouseY: 0, startW: 0, startH: 0 });

  const eventSourceRef = useRef(null);

  // Initialize modal position & size on open
  useEffect(() => {
    if (aiModalData) {
      setIsMaximized(false);
      const initialW = Math.min(window.innerWidth * 0.85, 880);
      const initialH = Math.min(window.innerHeight * 0.80, 640);
      setModalSize({ width: initialW, height: initialH });
      setModalPos({
        x: Math.max(16, (window.innerWidth - initialW) / 2),
        y: Math.max(24, (window.innerHeight - initialH) / 2)
      });
    }
  }, [aiModalData?.timestamp]);

  // Global mousemove and mouseup listeners for dragging and resizing
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (isDraggingRef.current && !isMaximized) {
        const dx = e.clientX - dragStartRef.current.mouseX;
        const dy = e.clientY - dragStartRef.current.mouseY;
        const newX = Math.max(10, Math.min(window.innerWidth - 120, dragStartRef.current.modalX + dx));
        const newY = Math.max(10, Math.min(window.innerHeight - 80, dragStartRef.current.modalY + dy));
        setModalPos({ x: newX, y: newY });
      }
      if (isResizingRef.current && !isMaximized) {
        const dx = e.clientX - resizeStartRef.current.mouseX;
        const dy = e.clientY - resizeStartRef.current.mouseY;
        const newW = Math.max(420, Math.min(window.innerWidth - 30, resizeStartRef.current.startW + dx));
        const newH = Math.max(300, Math.min(window.innerHeight - 30, resizeStartRef.current.startH + dy));
        setModalSize({ width: newW, height: newH });
      }
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      isResizingRef.current = false;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isMaximized]);

  const onDragStart = (e) => {
    if (isMaximized) return;
    // Don't drag if clicking buttons
    if (e.target.closest('button')) return;
    isDraggingRef.current = true;
    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      modalX: modalPos.x,
      modalY: modalPos.y
    };
  };

  const onResizeStart = (e) => {
    e.stopPropagation();
    if (isMaximized) return;
    isResizingRef.current = true;
    resizeStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startW: modalSize.width,
      startH: modalSize.height
    };
  };

  // 1. Setup Server-Sent Events (SSE) live connection
  useEffect(() => {
    let reconnectTimeout = null;

    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const sseUrl = `${API_BASE}/api/db/stream-realtime?token=${encodeURIComponent(token)}`;
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed && !parsed.error) {
            setLiveData(parsed);
          }
        } catch (e) {
          console.error("SSE parse error:", e);
        }
      };

      es.onerror = () => {
        setIsConnected(false);
        es.close();
        // Auto-reconnect after 3 seconds
        reconnectTimeout = setTimeout(connectSSE, 3000);
      };
    };

    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
    };
  }, [token, API_BASE]);

  // Fallback manual refresh
  const handleManualRefresh = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/db/snapshot-realtime`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setLiveData(data);
        setIsConnected(true);
      }
    } catch (e) {
      console.error("Manual snapshot failed:", e);
    }
  };

  // Terminate or Cancel PID
  const handleTerminatePid = async (dbLabel, pid, force = true) => {
    const actionDesc = force ? "KILL (Force Terminate)" : "CANCEL Query";
    if (!window.confirm(`คุณต้องการสั่ง ${actionDesc} บน Session PID ${pid} ของฐานข้อมูล [${dbLabel}] ใช่หรือไม่?`)) {
      return;
    }

    setTerminatingPid(pid);
    try {
      const res = await fetch(`${API_BASE}/api/db/terminate-pid`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ db_label: dbLabel, pid: pid, force: force })
      });
      const data = await res.json();
      if (res.ok) {
        alert(data.message || `ดำเนินการสำเร็จบน PID ${pid}`);
        handleManualRefresh();
      } else {
        alert(`เกิดข้อผิดพลาด: ${data.detail || 'ไม่สามารถสั่งคำสั่งได้'}`);
      }
    } catch (e) {
      alert(`Connection Error: ${e.message}`);
    } finally {
      setTerminatingPid(null);
    }
  };

  // AI Real-time Troubleshoot Trigger
  const handleAITroubleshoot = async (dbLabel, pid = null, query = null, lockInfo = null) => {
    setAiLoading(true);
    setAiModalData({
      dbLabel,
      pid,
      query,
      lockInfo,
      timestamp: Date.now(),
      recommendation: null
    });

    try {
      const res = await fetch(`${API_BASE}/api/db/ai-troubleshoot-realtime`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          db_label: dbLabel,
          pid: pid,
          query: query,
          lock_info: lockInfo
        })
      });
      if (res.ok) {
        const data = await res.json();
        setAiModalData(prev => ({ ...prev, recommendation: data.ai_recommendation }));
      } else {
        const err = await res.json();
        setAiModalData(prev => ({ ...prev, recommendation: `❌ AI Error: ${err.detail || 'Failed'}` }));
      }
    } catch (e) {
      setAiModalData(prev => ({ ...prev, recommendation: `❌ Network Error: ${e.message}` }));
    } finally {
      setAiLoading(false);
    }
  };

  // Helper formatting markdown
  const renderMarkdown = (text) => {
    if (!text) return null;
    return text.split('\n').map((line, idx) => {
      if (line.startsWith('### ')) {
        return <h4 key={idx} style={{ color: 'var(--color-primary)', marginTop: '16px', marginBottom: '8px', fontSize: '1.05rem' }}>{line.slice(4)}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} style={{ color: 'white', marginTop: '20px', marginBottom: '10px', fontSize: '1.15rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '4px' }}>{line.slice(3)}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={idx} style={{ color: 'var(--color-primary)', marginTop: '22px', marginBottom: '12px', fontSize: '1.25rem' }}>{line.slice(2)}</h2>;
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return (
          <div key={idx} style={{ display: 'flex', gap: '8px', margin: '4px 0', paddingLeft: '8px', color: '#e2e8f0', fontSize: '0.92rem' }}>
            <span style={{ color: 'var(--color-primary)' }}>•</span>
            <span>{line.slice(2)}</span>
          </div>
        );
      }
      if (line.trim().startsWith('```')) {
        return null;
      }
      if (!line.trim()) {
        return <div key={idx} style={{ height: '8px' }} />;
      }
      return <p key={idx} style={{ margin: '4px 0', lineHeight: 1.6, color: '#cbd5e1', fontSize: '0.92rem' }}>{line}</p>;
    });
  };

  const databases = liveData?.databases || [];
  const filteredDatabases = selectedDb === 'ALL' 
    ? databases 
    : databases.filter(d => d.label === selectedDb || d.host === selectedDb);

  // Aggregate all locks & queries
  const allLocks = filteredDatabases.flatMap(d => (d.lock_tree || []).map(l => ({ ...l, dbLabel: d.label })));
  const allActiveQueries = filteredDatabases.flatMap(d => (d.active_queries || []).map(q => ({ ...q, dbLabel: d.label })));

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* TOP HEADER & SSE STATUS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', minWidth: 0 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 700 }}>Real-time PostgreSQL Observability</h2>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '20px',
              background: isConnected ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              border: `1px solid ${isConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              color: isConnected ? '#34d399' : '#fb7185',
              fontSize: '0.75rem',
              fontWeight: 600
            }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: isConnected ? '#10b981' : '#f43f5e',
                boxShadow: isConnected ? '0 0 8px #10b981' : 'none',
                animation: isConnected ? 'pulse 1.5s infinite' : 'none'
              }} />
              <span>{isConnected ? 'SSE STREAM LIVE (2s)' : 'RECONNECTING...'}</span>
            </div>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            ตรวจจับ Lock Contention, คิวรีที่ค้าง, Wait Events, และวิเคราะห์ Root Cause แบบ Real-time ทันที
          </p>
        </div>

        {/* Database Selector & Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <select 
            value={selectedDb} 
            onChange={(e) => setSelectedDb(e.target.value)}
            className="glass-card"
            style={{
              padding: '10px 16px',
              background: 'rgba(15, 23, 42, 0.8)',
              color: 'white',
              border: '1px solid var(--glass-border)',
              borderRadius: '10px',
              outline: 'none',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: 600
            }}
          >
            <option value="ALL">🌐 All Databases Cluster ({databases.length})</option>
            {databases.map(d => (
              <option key={d.label} value={d.label}>🐘 {d.label} ({d.host})</option>
            ))}
          </select>

          <button
            onClick={handleManualRefresh}
            className="btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 14px' }}
          >
            <RefreshCw size={14} className={!isConnected ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* STATS SUMMARY METRICS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        
        {/* Total Active Connections */}
        <div className="glass-card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(6, 182, 212, 0.1)', color: 'var(--color-primary)' }}>
            <Activity size={24} />
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Active Connections</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'white' }}>
              {liveData?.total_active_connections ?? 0}
            </div>
          </div>
        </div>

        {/* Lock Conflicts / Blockers */}
        <div className="glass-card" style={{ 
          padding: '18px 20px', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '16px',
          borderColor: (liveData?.total_lock_conflicts || 0) > 0 ? 'rgba(244, 63, 94, 0.4)' : 'var(--glass-border)'
        }}>
          <div style={{ 
            padding: '12px', 
            borderRadius: '12px', 
            background: (liveData?.total_lock_conflicts || 0) > 0 ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.1)', 
            color: (liveData?.total_lock_conflicts || 0) > 0 ? 'var(--color-danger)' : 'var(--color-success)' 
          }}>
            <Lock size={24} />
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Lock Contention / Blocked</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: (liveData?.total_lock_conflicts || 0) > 0 ? 'var(--color-danger)' : 'white' }}>
              {liveData?.total_lock_conflicts ?? 0} {liveData?.total_lock_conflicts > 0 ? '🔥' : '✅'}
            </div>
          </div>
        </div>

        {/* Active Long Queries */}
        <div className="glass-card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(245, 158, 11, 0.1)', color: 'var(--color-warning)' }}>
            <Clock size={24} />
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Running Queries</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'white' }}>
              {allActiveQueries.length}
            </div>
          </div>
        </div>

        {/* Online Databases */}
        <div className="glass-card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(99, 102, 241, 0.1)', color: 'var(--color-secondary)' }}>
            <Database size={24} />
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Monitored DB Nodes</span>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'white' }}>
              {databases.filter(d => d.connected).length} / {databases.length}
            </div>
          </div>
        </div>

      </div>

      {/* NODE RESOURCE TELEMETRY (LIVE CPU, RAM, DISK R/W FOR MONITORED NODES) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
        gap: '16px'
      }}>
        {databases.map(d => {
          const cpuPct = d.cpu_pct ?? 0.0;
          const memPct = d.mem_pct ?? 0.0;
          const diskRead = d.disk_read_mb ?? 0.0;
          const diskWrite = d.disk_write_mb ?? 0.0;
          const cpuColor = cpuPct > 80 ? 'var(--color-danger)' : cpuPct > 50 ? 'var(--color-warning)' : 'var(--color-primary)';
          const memColor = memPct > 85 ? 'var(--color-danger)' : memPct > 70 ? 'var(--color-warning)' : '#818cf8';

          return (
            <div
              key={d.label}
              className="glass-card"
              style={{
                padding: '16px 18px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                background: 'rgba(15, 23, 42, 0.75)',
                borderColor: d.connected ? 'var(--glass-border)' : 'rgba(244, 63, 94, 0.3)'
              }}
            >
              {/* Node Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Server size={16} style={{ color: d.connected ? 'var(--color-primary)' : 'var(--color-danger)' }} />
                  <span style={{ fontWeight: 700, fontSize: '0.92rem', color: 'white' }}>{d.label}</span>
                </div>
                <span style={{
                  fontSize: '0.72rem',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  background: d.connected ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                  color: d.connected ? 'var(--color-success)' : 'var(--color-danger)',
                  fontWeight: 600
                }}>
                  {d.connected ? `Host: ${d.host}` : 'Disconnected'}
                </span>
              </div>

              {/* Resource Metrics Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                
                {/* CPU % */}
                <div style={{ background: 'rgba(0,0,0,0.25)', padding: '8px 10px', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Cpu size={12} style={{ color: cpuColor }} /> CPU
                    </span>
                    <strong style={{ color: cpuColor }}>{cpuPct.toFixed(1)}%</strong>
                  </div>
                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(cpuPct, 100)}%`, height: '100%', background: cpuColor, transition: 'width 0.5s ease' }} />
                  </div>
                </div>

                {/* Memory % */}
                <div style={{ background: 'rgba(0,0,0,0.25)', padding: '8px 10px', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Activity size={12} style={{ color: memColor }} /> RAM
                    </span>
                    <strong style={{ color: memColor }}>{memPct.toFixed(1)}%</strong>
                  </div>
                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(memPct, 100)}%`, height: '100%', background: memColor, transition: 'width 0.5s ease' }} />
                  </div>
                </div>

              </div>

              {/* Disk Read & Write MB/s */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 10px',
                background: 'rgba(0,0,0,0.25)',
                borderRadius: '8px',
                fontSize: '0.78rem',
                color: '#cbd5e1'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <HardDrive size={13} style={{ color: 'var(--color-primary)' }} />
                  <span>Disk I/O:</span>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <span>Read: <strong style={{ color: '#38bdf8' }}>{diskRead.toFixed(2)} MB/s</strong></span>
                  <span>Write: <strong style={{ color: '#fb923c' }}>{diskWrite.toFixed(2)} MB/s</strong></span>
                </div>
              </div>

            </div>
          );
        })}
      </div>

      {/* NAVIGATION TABS */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '8px' }}>
        <button
          onClick={() => setActiveTab('locks')}
          style={{
            padding: '10px 18px',
            borderRadius: '10px',
            border: 'none',
            background: activeTab === 'locks' ? 'rgba(244, 63, 94, 0.15)' : 'transparent',
            color: activeTab === 'locks' ? 'var(--color-danger)' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer'
          }}
        >
          <Lock size={16} />
          <span>Lock Trees & Blockers ({allLocks.length})</span>
          {allLocks.length > 0 && <span style={{ background: 'var(--color-danger)', color: 'white', fontSize: '0.7rem', padding: '2px 6px', borderRadius: '10px' }}>ALERT</span>}
        </button>

        <button
          onClick={() => setActiveTab('queries')}
          style={{
            padding: '10px 18px',
            borderRadius: '10px',
            border: 'none',
            background: activeTab === 'queries' ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
            color: activeTab === 'queries' ? 'var(--color-primary)' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer'
          }}
        >
          <Activity size={16} />
          <span>Active & Slow Queries ({allActiveQueries.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('wait_events')}
          style={{
            padding: '10px 18px',
            borderRadius: '10px',
            border: 'none',
            background: activeTab === 'wait_events' ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
            color: activeTab === 'wait_events' ? 'var(--color-secondary)' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer'
          }}
        >
          <HardDrive size={16} />
          <span>Wait Events & Disk I/O</span>
        </button>

        <button
          onClick={() => setActiveTab('pgbouncer')}
          style={{
            padding: '10px 18px',
            borderRadius: '10px',
            border: 'none',
            background: activeTab === 'pgbouncer' ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
            color: activeTab === 'pgbouncer' ? 'var(--color-success)' : 'var(--text-secondary)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer'
          }}
        >
          <Server size={16} />
          <span>Connection Pools & Queues</span>
        </button>
      </div>

      {/* TAB CONTENT 1: LOCK TREE & BLOCKERS */}
      {activeTab === 'locks' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {allLocks.length === 0 ? (
            <div className="glass-card" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <CheckCircle2 size={48} style={{ color: 'var(--color-success)', marginBottom: '12px', opacity: 0.8 }} />
              <h3 style={{ color: 'white', marginBottom: '6px' }}>No Lock Contention Detected</h3>
              <p style={{ fontSize: '0.9rem' }}>ระบบฐานข้อมูลทำงานปกติ ไม่พบคิวรีที่ติด Lock ตารางหรือมี Blocker Session ในขณะนี้</p>
            </div>
          ) : (
            allLocks.map((lock, idx) => (
              <div key={idx} className="glass-card" style={{ padding: '24px', border: '1px solid rgba(244, 63, 94, 0.3)', background: 'rgba(30, 20, 30, 0.6)' }}>
                
                {/* Header with Blocker Badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ background: 'var(--color-danger)', color: 'white', fontSize: '0.75rem', fontWeight: 700, padding: '4px 10px', borderRadius: '6px' }}>
                      🔥 LOCK CONFLICT #{idx + 1}
                    </span>
                    <span style={{ color: 'white', fontWeight: 600 }}>Database: {lock.dbLabel}</span>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Type: {lock.lock_type} ({lock.lock_mode})</span>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => handleAITroubleshoot(lock.dbLabel, lock.blocking_pid, lock.blocking_statement, lock)}
                      className="btn-primary"
                      style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <Bot size={14} />
                      <span>AI Troubleshoot Lock</span>
                    </button>

                    <button
                      onClick={() => handleTerminatePid(lock.dbLabel, lock.blocking_pid, true)}
                      disabled={terminatingPid === lock.blocking_pid}
                      style={{
                        background: 'rgba(244, 63, 94, 0.2)',
                        border: '1px solid rgba(244, 63, 94, 0.4)',
                        color: '#fb7185',
                        borderRadius: '8px',
                        padding: '8px 14px',
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}
                    >
                      <Square size={14} />
                      <span>{terminatingPid === lock.blocking_pid ? 'Killing...' : `Kill Blocker PID ${lock.blocking_pid}`}</span>
                    </button>
                  </div>
                </div>

                {/* BLOCKER VS BLOCKED CORRELATION GRAPH */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: '16px', alignItems: 'center' }}>
                  
                  {/* LEFT: BLOCKER (ต้นเหตุ) */}
                  <div style={{ background: 'rgba(244, 63, 94, 0.08)', border: '1px solid rgba(244, 63, 94, 0.2)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ color: '#fb7185', fontWeight: 700, fontSize: '0.9rem' }}>⛔ BLOCKER (ผู้ถือ Lock)</span>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Duration: {lock.blocking_duration_sec}s</span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '6px' }}>
                      <strong>PID:</strong> {lock.blocking_pid} | <strong>User:</strong> {lock.blocking_user} | <strong>State:</strong> <code style={{ color: '#fca5a5' }}>{lock.blocking_state}</code>
                    </div>
                    <pre style={{
                      background: 'rgba(0, 0, 0, 0.4)',
                      padding: '10px',
                      borderRadius: '8px',
                      fontSize: '0.8rem',
                      color: '#fecaca',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '120px',
                      overflowY: 'auto'
                    }}>
                      {lock.blocking_statement || '(No active query / idle in transaction)'}
                    </pre>
                  </div>

                  {/* CENTER ARROW */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', color: 'var(--color-danger)' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700 }}>BLOCKS</span>
                    <ChevronRight size={28} />
                  </div>

                  {/* RIGHT: BLOCKED VICTIM (ผู้ที่ถูกขัดขวาง) */}
                  <div style={{ background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.2)', borderRadius: '12px', padding: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ color: '#fbbf24', fontWeight: 700, fontSize: '0.9rem' }}>🔒 WAITING (ค้างรอ Lock)</span>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Waiting: {lock.blocked_duration_sec}s</span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '6px' }}>
                      <strong>PID:</strong> {lock.blocked_pid} | <strong>User:</strong> {lock.blocked_user} | <strong>Event:</strong> {lock.blocked_wait_type}/{lock.blocked_wait_event}
                    </div>
                    <pre style={{
                      background: 'rgba(0, 0, 0, 0.4)',
                      padding: '10px',
                      borderRadius: '8px',
                      fontSize: '0.8rem',
                      color: '#fde68a',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '120px',
                      overflowY: 'auto'
                    }}>
                      {lock.blocked_statement}
                    </pre>
                  </div>

                </div>

              </div>
            ))
          )}
        </div>
      )}

      {/* TAB CONTENT 2: ACTIVE & SLOW QUERIES */}
      {activeTab === 'queries' && (
        <div className="glass-card" style={{ padding: '20px', overflowX: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '1.1rem' }}>Active Queries Streaming Live</h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Showing top running queries</span>
          </div>

          {allActiveQueries.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
              <p>No active long-running queries currently executing.</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--glass-border)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '10px' }}>DB</th>
                  <th style={{ padding: '10px' }}>PID</th>
                  <th style={{ padding: '10px' }}>User / Client</th>
                  <th style={{ padding: '10px' }}>Duration</th>
                  <th style={{ padding: '10px' }}>Wait Event</th>
                  <th style={{ padding: '10px' }}>Query Statement</th>
                  <th style={{ padding: '10px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {allActiveQueries.map((q, qidx) => {
                  const isSlow = q.duration_sec > 10;
                  const isCrit = q.duration_sec > 30;
                  const isBlocked = q.blocking_pids && q.blocking_pids.length > 0;
                  return (
                    <tr key={qidx} style={{ 
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      background: isBlocked ? 'rgba(244, 63, 94, 0.08)' : isCrit ? 'rgba(245, 158, 11, 0.05)' : 'transparent'
                    }}>
                      <td style={{ padding: '10px', fontWeight: 600, color: 'var(--color-primary)' }}>{q.dbLabel}</td>
                      <td style={{ padding: '10px', fontFamily: 'monospace' }}>{q.pid}</td>
                      <td style={{ padding: '10px' }}>
                        <div>{q.usename}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{q.client_addr || 'local'}</div>
                      </td>
                      <td style={{ padding: '10px' }}>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '4px',
                          fontWeight: 700,
                          fontSize: '0.8rem',
                          background: isCrit ? 'rgba(244, 63, 94, 0.2)' : isSlow ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.15)',
                          color: isCrit ? '#f43f5e' : isSlow ? '#f59e0b' : '#10b981'
                        }}>
                          {q.duration_sec}s
                        </span>
                      </td>
                      <td style={{ padding: '10px' }}>
                        {isBlocked ? (
                          <span style={{ color: 'var(--color-danger)', fontWeight: 700 }}>⛔ Blocked by PID {q.blocking_pids.join(',')}</span>
                        ) : (
                          <span style={{ color: q.wait_event_type === 'IO' ? '#f59e0b' : 'var(--text-secondary)' }}>
                            {q.wait_event_type}: {q.wait_event}
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '10px', maxWidth: '350px' }}>
                        <div style={{ 
                          fontFamily: 'monospace', 
                          fontSize: '0.8rem', 
                          color: '#e2e8f0', 
                          overflow: 'hidden', 
                          textOverflow: 'ellipsis', 
                          whiteSpace: 'nowrap' 
                        }} title={q.query}>
                          {q.query}
                        </div>
                      </td>
                      <td style={{ padding: '10px', textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                          <button
                            onClick={() => handleAITroubleshoot(q.dbLabel, q.pid, q.query)}
                            style={{
                              background: 'rgba(6, 182, 212, 0.15)',
                              border: '1px solid rgba(6, 182, 212, 0.3)',
                              color: 'var(--color-primary)',
                              padding: '5px 8px',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 600
                            }}
                          >
                            🤖 AI Help
                          </button>
                          <button
                            onClick={() => handleTerminatePid(q.dbLabel, q.pid, true)}
                            disabled={terminatingPid === q.pid}
                            style={{
                              background: 'rgba(244, 63, 94, 0.15)',
                              border: '1px solid rgba(244, 63, 94, 0.3)',
                              color: 'var(--color-danger)',
                              padding: '5px 8px',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 600
                            }}
                          >
                            Kill
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* TAB CONTENT 3: WAIT EVENTS & DISK I/O */}
      {activeTab === 'wait_events' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
          {filteredDatabases.map(db => (
            <div key={db.label} className="glass-card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <h4 style={{ fontSize: '1.05rem', color: 'white' }}>🐘 {db.label} Wait Events</h4>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-primary)' }}>{db.host}:{db.port}</span>
              </div>

              {(!db.wait_events || db.wait_events.length === 0) ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active wait events recorded.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {db.wait_events.map((w, widx) => (
                    <div key={widx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '0.85rem', color: w.wait_type === 'Lock' ? 'var(--color-danger)' : w.wait_type === 'IO' ? 'var(--color-warning)' : 'var(--color-primary)' }}>
                          {w.wait_type}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{w.wait_event}</div>
                      </div>
                      <span style={{ background: 'rgba(255,255,255,0.1)', padding: '3px 8px', borderRadius: '12px', fontSize: '0.8rem', fontWeight: 700 }}>
                        {w.count} connections
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* TAB CONTENT 4: PGBOUNCER & HIKARICP POOLS */}
      {activeTab === 'pgbouncer' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
          
          {/* PgBouncer Metrics */}
          <div className="glass-card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '1.05rem', marginBottom: '14px', color: 'white', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Server size={18} style={{ color: 'var(--color-primary)' }} />
              <span>PgBouncer Connection Pools (Port 6432)</span>
            </h4>

            {Object.keys(liveData?.pgbouncer || {}).length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No PgBouncer pool metrics available.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {Object.entries(liveData.pgbouncer).map(([dbname, p]) => {
                  const hasQueue = (p.waiting || 0) > 0;
                  return (
                    <div key={dbname} style={{
                      padding: '12px',
                      borderRadius: '8px',
                      background: hasQueue ? 'rgba(244, 63, 94, 0.1)' : 'rgba(255, 255, 255, 0.03)',
                      border: `1px solid ${hasQueue ? 'rgba(244, 63, 94, 0.3)' : 'var(--glass-border)'}`
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                        <span style={{ fontWeight: 600, color: 'white' }}>Pool: {dbname}</span>
                        <span style={{ fontSize: '0.8rem', color: hasQueue ? 'var(--color-danger)' : 'var(--color-success)', fontWeight: 700 }}>
                          {hasQueue ? `⚠️ ${p.waiting} Waiting Clients` : '✅ 0 Waiting'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        <span>Active Connections: <strong>{p.active}</strong></span>
                        <span>Waiting Queue: <strong style={{ color: hasQueue ? 'var(--color-danger)' : 'inherit' }}>{p.waiting}</strong></span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Spring Boot HikariCP Metrics */}
          <div className="glass-card" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '1.05rem', marginBottom: '14px', color: 'white', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} style={{ color: 'var(--color-warning)' }} />
              <span>Spring Boot Actuator (HikariCP & JVM)</span>
            </h4>

            {Object.keys(liveData?.springboot || {}).length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No Spring Boot Actuator connection pool metrics found.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {Object.entries(liveData.springboot).map(([app, sb]) => (
                  <div key={app} style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--color-warning)', marginBottom: '6px' }}>{app}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <div>Hikari Active: <strong>{sb.hikari_active}/{sb.hikari_max}</strong></div>
                      <div>Pending Queue: <strong style={{ color: sb.hikari_pending > 0 ? 'var(--color-danger)' : 'inherit' }}>{sb.hikari_pending}</strong></div>
                      <div>JVM Heap: <strong>{sb.jvm_heap_pct}%</strong></div>
                      <div>GC Pause: <strong>{sb.gc_pause_max_s}s</strong></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      )}

      {/* AI TROUBLESHOOTING MODAL / FLOATING PANEL (DRAGGABLE & RESIZABLE) */}
      {aiModalData && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(6px)',
          zIndex: 9999,
          pointerEvents: 'auto'
        }}>
          <div
            className="glass-card"
            style={{
              position: 'fixed',
              left: isMaximized ? '16px' : `${modalPos.x}px`,
              top: isMaximized ? '16px' : `${modalPos.y}px`,
              width: isMaximized ? 'calc(100vw - 32px)' : `${modalSize.width}px`,
              height: isMaximized ? 'calc(100vh - 32px)' : `${modalSize.height}px`,
              maxWidth: 'calc(100vw - 20px)',
              maxHeight: 'calc(100vh - 20px)',
              display: 'flex',
              flexDirection: 'column',
              background: 'rgba(15, 23, 42, 0.98)',
              borderColor: 'var(--color-primary)',
              boxShadow: '0 25px 60px rgba(0,0,0,0.8), 0 0 20px rgba(6, 182, 212, 0.25)',
              borderRadius: '16px',
              padding: 0,
              overflow: 'hidden',
              userSelect: isDraggingRef.current ? 'none' : 'auto',
              boxSizing: 'border-box'
            }}
          >
            {/* Modal Header (Drag Handle) */}
            <div
              onMouseDown={onDragStart}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '14px 20px',
                borderBottom: '1px solid var(--glass-border)',
                background: 'rgba(30, 41, 59, 0.7)',
                cursor: isMaximized ? 'default' : 'grab',
                flexShrink: 0
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(6, 182, 212, 0.15)', color: 'var(--color-primary)' }}>
                  <Bot size={22} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, color: 'white' }}>
                      Real-time AI Root Cause Troubleshooter
                    </h3>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: '4px' }}>
                      {isMaximized ? 'เต็มจอ' : 'ลากย้ายได้'}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.8rem', color: 'var(--color-primary)' }}>
                    Target DB: <strong>{aiModalData.dbLabel}</strong> {aiModalData.pid ? `| PID: ${aiModalData.pid}` : ''}
                  </span>
                </div>
              </div>

              {/* Window Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={() => setIsMaximized(prev => !prev)}
                  className="btn-secondary"
                  title={isMaximized ? 'ย่อขนาด (Restore)' : 'ขยายเต็มจอ (Maximize)'}
                  style={{ padding: '6px 10px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button
                  onClick={() => setAiModalData(null)}
                  className="btn-secondary"
                  title="ปิด (Close)"
                  style={{ padding: '6px 10px', borderRadius: '8px', color: 'var(--color-danger)', borderColor: 'rgba(244, 63, 94, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Modal Body with smooth scrolling */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px',
              fontSize: '0.92rem',
              lineHeight: 1.7,
              color: '#e2e8f0'
            }}>
              {aiLoading ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '260px', gap: '16px' }}>
                  <RefreshCw size={36} className="spin" style={{ color: 'var(--color-primary)' }} />
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>AI กำลัง Execute ตรวจสอบ Blocker สด และวิเคราะห์แนวทางแก้ไขแบบ Real-time...</p>
                </div>
              ) : (
                <div>
                  {renderMarkdown(aiModalData.recommendation)}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            {!aiLoading && aiModalData.recommendation && (
              <div style={{
                padding: '14px 20px',
                borderTop: '1px solid var(--glass-border)',
                background: 'rgba(15, 23, 42, 0.95)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexShrink: 0
              }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  💡 สามารถลากมุมขวาล่างเพื่อย่อ/ขยาย หรือกดปุ่ม ⛶ ขยายเต็มจอได้
                </span>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(aiModalData.recommendation);
                      setCopySuccess(true);
                      setTimeout(() => setCopySuccess(false), 2000);
                    }}
                    className="btn-secondary"
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px' }}
                  >
                    {copySuccess ? <Check size={14} style={{ color: 'var(--color-success)' }} /> : <Copy size={14} />}
                    <span>{copySuccess ? 'คัดลอกแล้ว!' : 'คัดลอกคำแนะนำ'}</span>
                  </button>
                  <button
                    onClick={() => setAiModalData(null)}
                    className="btn-primary"
                    style={{ padding: '8px 18px' }}
                  >
                    เสร็จสิ้น
                  </button>
                </div>
              </div>
            )}

            {/* Resizing Handle (Corner Grip) */}
            {!isMaximized && (
              <div
                onMouseDown={onResizeStart}
                style={{
                  position: 'absolute',
                  right: 0,
                  bottom: 0,
                  width: '20px',
                  height: '20px',
                  cursor: 'nwse-resize',
                  zIndex: 10,
                  display: 'flex',
                  alignItems: 'flex-end',
                  justifyContent: 'flex-end',
                  padding: '3px'
                }}
              >
                <div style={{
                  width: '10px',
                  height: '10px',
                  borderRight: '2px solid var(--color-primary)',
                  borderBottom: '2px solid var(--color-primary)',
                  opacity: 0.6
                }} />
              </div>
            )}

          </div>
        </div>
      )}

    </div>
  );
}
