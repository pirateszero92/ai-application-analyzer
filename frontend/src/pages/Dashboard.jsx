import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Clock, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Loader2, 
  RefreshCw, 
  FileText, 
  Database,
  Terminal as ConsoleIcon,
  ChevronRight,
  Cpu,
  Trash2
} from 'lucide-react';

export default function Dashboard({ token, API_BASE }) {
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [selectedDailyNum, setSelectedDailyNum] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [activeTab, setActiveTab] = useState('summary');
  const [liveHealth, setLiveHealth] = useState(null);
  const [triggeringHealth, setTriggeringHealth] = useState(false);
  const [diagnosingHealth, setDiagnosingHealth] = useState(false);
  const [showDiagnosisModal, setShowDiagnosisModal] = useState(false);
  const pollIntervalRef = useRef(null);
  const selectedReportRef = useRef(null);

  const fetchLiveHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health/live`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setLiveHealth(data);
      }
    } catch (e) {
      console.error("Failed to fetch live health:", e);
    }
  };

  const handleTriggerHealthCheck = async () => {
    setTriggeringHealth(true);
    try {
      const res = await fetch(`${API_BASE}/api/health/trigger`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setTimeout(fetchLiveHealth, 3000);
      }
    } catch (e) {
      console.error("Failed to trigger health check:", e);
    } finally {
      setTriggeringHealth(false);
    }
  };

  const handleTriggerAIDiagnosis = async (eventId) => {
    if (!eventId) return;
    setDiagnosingHealth(true);
    try {
      const res = await fetch(`${API_BASE}/api/health/diagnose/${eventId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const updated = await res.json();
        setLiveHealth(updated);
      }
    } catch (e) {
      console.error("Failed to trigger AI diagnosis:", e);
    } finally {
      setDiagnosingHealth(false);
    }
  };

  const getLocalDateString = (timestampStr) => {
    const d = new Date(timestampStr);
    return d.toLocaleDateString('th-TH', { year: 'numeric', month: '2-digit', day: '2-digit' });
  };

  const getGroupedReports = (flatReports) => {
    const groups = {};
    const sortedReports = [...flatReports].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    sortedReports.forEach((r) => {
      const dateKey = getLocalDateString(r.timestamp);
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      const dailyNum = groups[dateKey].length + 1;
      groups[dateKey].push({
        ...r,
        dailyNum
      });
    });
    const groupedList = Object.keys(groups).map((dateKey) => {
      return {
        date: dateKey,
        reports: [...groups[dateKey]].reverse()
      };
    }).sort((a, b) => {
      return new Date(b.reports[0].timestamp) - new Date(a.reports[0].timestamp);
    });
    return groupedList;
  };

  // Sync selectedReportRef with state to prevent stale closures in polling
  useEffect(() => {
    selectedReportRef.current = selectedReport;
  }, [selectedReport]);

  useEffect(() => {
    fetchReports(true);
    fetchLiveHealth();
    const interval = setInterval(() => {
      fetchReports(false);
      fetchLiveHealth();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchReports = async (selectFirst = false) => {
    try {
      const response = await fetch(`${API_BASE}/api/reports`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setReports(data);
        if (selectFirst && data.length > 0) {
          fetchReportDetail(data[0].id, null, data);
        }
        
        // Auto-refresh selected report details if it completes running in background
        const currentSelected = selectedReportRef.current;
        if (currentSelected && currentSelected.status === 'running') {
          const updatedSel = data.find(r => r.id === currentSelected.id);
          if (updatedSel && updatedSel.status !== 'running') {
            fetchReportDetail(currentSelected.id, null, data);
          }
        }
      }
    } catch (e) {
      console.error("Failed to fetch reports:", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchReportDetail = async (id, dailyNum = null, latestReports = null) => {
    try {
      const listToSearch = latestReports || reports;
      let foundNum = dailyNum;
      if (!foundNum && listToSearch && listToSearch.length > 0) {
        const grouped = getGroupedReports(listToSearch);
        for (const group of grouped) {
          const found = group.reports.find(rep => rep.id === id);
          if (found) {
            foundNum = found.dailyNum;
            break;
          }
        }
      }
      setSelectedDailyNum(foundNum);

      const response = await fetch(`${API_BASE}/api/reports/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setSelectedReport(data);
      }
    } catch (e) {
      console.error("Failed to fetch report detail:", e);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      const response = await fetch(`${API_BASE}/api/reports/trigger`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const newReport = await response.json();
        setReports(prev => {
          const updated = [newReport, ...prev];
          fetchReportDetail(newReport.id, null, updated);
          return updated;
        });
      }
    } catch (e) {
      console.error("Failed to trigger analysis:", e);
    } finally {
      setTriggering(false);
    }
  };

  const handleDeleteReport = async (reportId) => {
    if (!window.confirm(`คุณต้องการลบผลการวิเคราะห์ Run #${reportId} ใช่หรือไม่? ข้อมูลและประวัติใน S3/MinIO จะถูกลบออกถาวร`)) {
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE}/api/reports/${reportId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        // Deselect
        setSelectedReport(curr => curr && curr.id === reportId ? null : curr);
        fetchReports();
      } else {
        alert("เกิดข้อผิดพลาดในการลบรายการ");
      }
    } catch (e) {
      console.error("Error deleting report:", e);
      alert("ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้");
    }
  };

  // Helper to parse dates
  const formatDate = (dateStr) => {
    const d = new Date(dateStr);
    return d.toLocaleString('th-TH', { 
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  // Render markdown tags with basic custom regex to look premium
  const renderMarkdown = (text) => {
    if (!text) return <p>ไม่มีรายงานวิเคราะห์</p>;

    // Split lines
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      // Headers
      if (line.startsWith('### ')) {
        return <h4 key={idx} style={{ color: 'var(--color-primary)', marginTop: '20px', marginBottom: '10px', fontSize: '1.15rem' }}>{line.slice(4)}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} style={{ color: 'var(--color-primary)', marginTop: '24px', marginBottom: '12px', fontSize: '1.3rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '6px' }}>{line.slice(3)}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={idx} style={{ color: 'white', marginTop: '28px', marginBottom: '16px', fontSize: '1.6rem' }}>{line.slice(2)}</h2>;
      }

      // Bullet lists
      if (line.startsWith('* ') || line.startsWith('- ')) {
        // Parse bold elements in bullet point
        const content = line.slice(2);
        return (
          <li key={idx} style={{ marginLeft: '20px', marginBottom: '8px', color: 'var(--text-primary)', listStyleType: 'square' }}>
            {parseBoldText(content)}
          </li>
        );
      }

      // Bold key points or plain text
      if (line.trim() === '') {
        return <div key={idx} style={{ height: '12px' }} />;
      }

      return <p key={idx} style={{ marginBottom: '10px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>{parseBoldText(line)}</p>;
    });
  };

  // Helper to parse **bold** text in markdown
  const parseBoldText = (text) => {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        return <strong key={i} style={{ color: 'white', fontWeight: 700 }}>{part}</strong>;
      }
      return part;
    });
  };

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
      
      {/* Top Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '20px'
      }}>
        <div>
          <h2 style={{ fontSize: '2rem', marginBottom: '6px' }}>DevOps AI Dashboard</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
            ประมวลผลประสิทธิภาพและวิเคราะห์คอขวดของระบบ WMS/TMS Production ในระดับวินาที
          </p>
        </div>

        <button 
          onClick={handleTrigger}
          disabled={triggering || (selectedReport && selectedReport.status === 'running')}
          className="btn-primary"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 24px'
          }}
        >
          {triggering || (selectedReport && selectedReport.status === 'running') ? (
            <>
              <Loader2 className="spin" size={18} style={{ animation: 'spin 2s linear infinite' }} />
              <span>Analyzing...</span>
            </>
          ) : (
            <>
              <Play size={18} />
              <span>Trigger Analysis</span>
            </>
          )}
        </button>
      </div>

      {/* Proactive Health Status Banner */}
      {liveHealth && (
        <div className="glass-card fade-in" style={{
          padding: '18px 24px',
          background: liveHealth.status === 'critical' 
            ? 'linear-gradient(135deg, rgba(244,63,94,0.15) 0%, rgba(15,23,42,0.6) 100%)'
            : liveHealth.status === 'warning'
            ? 'linear-gradient(135deg, rgba(234,179,8,0.15) 0%, rgba(15,23,42,0.6) 100%)'
            : 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(15,23,42,0.6) 100%)',
          border: `1px solid ${
            liveHealth.status === 'critical' ? 'rgba(244,63,94,0.4)' : liveHealth.status === 'warning' ? 'rgba(234,179,8,0.4)' : 'rgba(16,185,129,0.3)'
          }`,
          display: 'flex',
          justify: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px'
        }}>
          {/* Health Score & Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: liveHealth.status === 'critical' ? 'rgba(244,63,94,0.2)' : liveHealth.status === 'warning' ? 'rgba(234,179,8,0.2)' : 'rgba(16,185,129,0.2)',
              border: `2px solid ${liveHealth.status === 'critical' ? '#f43f5e' : liveHealth.status === 'warning' ? '#eab308' : '#10b981'}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '1.2rem',
              color: liveHealth.status === 'critical' ? '#f43f5e' : liveHealth.status === 'warning' ? '#eab308' : '#10b981'
            }}>
              {liveHealth.health_score}
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                <span style={{ fontWeight: 700, fontSize: '1.05rem', color: 'white' }}>
                  Proactive Health Status:
                </span>
                <span style={{
                  padding: '3px 10px',
                  borderRadius: '12px',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  background: liveHealth.status === 'critical' ? 'rgba(244,63,94,0.2)' : liveHealth.status === 'warning' ? 'rgba(234,179,8,0.2)' : 'rgba(16,185,129,0.2)',
                  color: liveHealth.status === 'critical' ? '#f43f5e' : liveHealth.status === 'warning' ? '#eab308' : '#10b981',
                  border: `1px solid ${liveHealth.status === 'critical' ? 'rgba(244,63,94,0.4)' : liveHealth.status === 'warning' ? 'rgba(234,179,8,0.4)' : 'rgba(16,185,129,0.3)'}`
                }}>
                  {liveHealth.status}
                </span>
              </div>
              
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {liveHealth.alerts_json && JSON.parse(liveHealth.alerts_json).length > 0 ? (
                  <span style={{ color: liveHealth.status === 'critical' ? '#f43f5e' : '#eab308', fontWeight: 600 }}>
                    ⚠️ ตรวจพบ {JSON.parse(liveHealth.alerts_json).length} Alert ในระบบ WMS/TMS ({formatDate(liveHealth.timestamp)})
                  </span>
                ) : (
                  <span style={{ color: '#10b981' }}>
                    ✅ ระบบทำงานได้สมบูรณ์ ไม่พบปัญหาหรือจุดคอขวด ({formatDate(liveHealth.timestamp)})
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => setShowDiagnosisModal(true)}
              className="btn-secondary"
              style={{
                padding: '8px 16px',
                fontSize: '0.85rem',
                borderColor: 'rgba(56,189,248,0.5)',
                color: '#38bdf8',
                background: 'rgba(56,189,248,0.12)',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontWeight: 600
              }}
            >
              <span>📖 อ่านผลวิเคราะห์ Proactive</span>
            </button>

            <button
              onClick={handleTriggerHealthCheck}
              disabled={triggeringHealth}
              className="btn-secondary"
              style={{ padding: '8px 16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <RefreshCw className={triggeringHealth ? "spin" : ""} size={14} style={{ animation: triggeringHealth ? 'spin 2s linear infinite' : 'none' }} />
              <span>{triggeringHealth ? "Checking..." : "Check Health Now"}</span>
            </button>
          </div>
        </div>
      )}

      {/* AI Diagnosis Modal */}
      {showDiagnosisModal && liveHealth && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.8)',
          backdropFilter: 'blur(8px)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px'
        }}>
          <div className="glass-card fade-in" style={{
            width: '100%',
            maxWidth: '900px',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '32px',
            border: '1px solid rgba(56,189,248,0.3)',
            boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '1.4rem', color: '#38bdf8', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>🧠 AI Real-time Health & Root Cause Analysis</span>
                </h3>
                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  ตรวจสอบ ณ เวลา {formatDate(liveHealth.timestamp)} (Health Score: {liveHealth.health_score}/100 - {liveHealth.status.toUpperCase()})
                </span>
              </div>
              <button 
                onClick={() => setShowDiagnosisModal(false)}
                className="btn-secondary"
                style={{ padding: '6px 14px', fontSize: '0.85rem' }}
              >
                ✕ ปิดหน้าต่าง
              </button>
            </div>

            {/* Active Alerts List */}
            {liveHealth.alerts_json && JSON.parse(liveHealth.alerts_json).length > 0 && (
              <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(244,63,94,0.08)', borderRadius: '10px', border: '1px solid rgba(244,63,94,0.2)' }}>
                <h4 style={{ color: '#f43f5e', marginBottom: '10px', fontSize: '0.95rem' }}>⚠️ รายการ Anomaly ที่ตรวจพบ ({JSON.parse(liveHealth.alerts_json).length} รายการ):</h4>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                  {JSON.parse(liveHealth.alerts_json).map((a, i) => (
                    <li key={i} style={{ color: 'var(--text-primary)', fontSize: '0.88rem', marginBottom: '4px' }}>{a}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Full AI Diagnosis Content */}
            {liveHealth.ai_diagnosis ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h4 style={{ color: '#38bdf8', margin: 0 }}>ผลวิเคราะห์และคำแนะนำจาก AI:</h4>
                  <button
                    onClick={() => handleTriggerAIDiagnosis(liveHealth.id)}
                    disabled={diagnosingHealth}
                    className="btn-secondary"
                    style={{ padding: '4px 12px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    <RefreshCw className={diagnosingHealth ? "spin" : ""} size={12} style={{ animation: diagnosingHealth ? 'spin 2s linear infinite' : 'none' }} />
                    <span>{diagnosingHealth ? "กำลังวิเคราะห์ซ้ำ..." : "วิเคราะห์ซ้ำ"}</span>
                  </button>
                </div>
                <div style={{ color: 'var(--text-primary)', lineHeight: 1.6, background: 'rgba(15,23,42,0.4)', padding: '20px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                  {renderMarkdown(liveHealth.ai_diagnosis)}
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '36px 16px', background: 'rgba(15,23,42,0.6)', borderRadius: '12px', border: '1px dashed rgba(56,189,248,0.3)' }}>
                <h4 style={{ color: '#38bdf8', marginBottom: '8px' }}>สั่ง AI วิเคราะห์ Root Cause เชิงลึก</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '20px' }}>
                  กดปุ่มด้านล่างเพื่อเรียก AI ให้วิเคราะห์หา Root Cause และแนวทางแก้ไขทันที
                </p>
                <button
                  onClick={() => handleTriggerAIDiagnosis(liveHealth.id)}
                  disabled={diagnosingHealth}
                  className="btn-primary"
                  style={{ padding: '10px 24px', display: 'inline-flex', alignItems: 'center', gap: '8px', margin: '0 auto' }}
                >
                  {diagnosingHealth ? (
                    <>
                      <RefreshCw className="spin" size={18} style={{ animation: 'spin 2s linear infinite' }} />
                      <span>กำลังวิเคราะห์โดย AI...</span>
                    </>
                  ) : (
                    <>
                      <Cpu size={18} />
                      <span>🤖 สั่ง AI วิเคราะห์ Root Cause ตอนนี้</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Grid */}
      <div className="dashboard-grid">
        
        {/* Left Side: Recent Runs List */}
        <section className="glass-card" style={{
          padding: '24px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          maxHeight: 'calc(100vh - 200px)',
          overflowY: 'auto'
        }}>
          <h3 style={{ fontSize: '1.1rem', paddingLeft: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Recent Runs</span>
            <button 
              onClick={() => fetchReports()} 
              style={{ background: 'none', border: 'none', color: 'var(--color-primary)' }}
            >
              <RefreshCw size={14} />
            </button>
          </h3>

          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
              <Loader2 className="spin" size={24} style={{ display: 'inline', animation: 'spin 2s linear infinite' }} />
              <p style={{ marginTop: '10px' }}>Loading runs...</p>
            </div>
          ) : reports.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 10px', color: 'var(--text-muted)' }}>
              <AlertCircle size={24} style={{ display: 'inline', marginBottom: '8px' }} />
              <p>No analysis runs found.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {getGroupedReports(reports).map((group) => (
                <div key={group.date} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {/* Date Header */}
                  <div style={{
                    fontSize: '0.78rem',
                    color: 'var(--color-primary)',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    paddingBottom: '4px',
                    borderBottom: '1px dashed var(--glass-border)',
                    marginBottom: '4px',
                    paddingLeft: '8px'
                  }}>
                    {group.date}
                  </div>
                  
                  {/* Runs list */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {group.reports.map((r) => {
                      const isSelected = selectedReport && selectedReport.id === r.id;
                      return (
                        <div 
                          key={r.id}
                          onClick={() => fetchReportDetail(r.id, r.dailyNum)}
                          className="glass-card"
                          style={{
                            padding: '14px 16px',
                            cursor: 'pointer',
                            background: isSelected ? 'rgba(255, 255, 255, 0.05)' : 'rgba(30, 41, 59, 0.2)',
                            borderColor: isSelected ? 'var(--color-primary)' : 'var(--glass-border)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px'
                          }}
                        >
                          {/* Status Icon */}
                          {r.status === 'success' && <CheckCircle size={18} style={{ color: 'var(--color-success)' }} />}
                          {r.status === 'failed' && <XCircle size={18} style={{ color: 'var(--color-danger)' }} />}
                          {r.status === 'running' && (
                            <Loader2 className="spin" size={18} style={{ color: 'var(--color-primary)', animation: 'spin 2s linear infinite' }} />
                          )}

                          <div style={{ flex: 1, overflow: 'hidden' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Run #{r.dailyNum}</span>
                              {r.status === 'running' && (
                                <span style={{ fontSize: '0.75rem', color: 'var(--color-primary)', fontWeight: 600 }}>Analyzing</span>
                              )}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Clock size={12} />
                              <span>{formatDate(r.timestamp).split(' ')[1] /* Only show time */}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Right Side: Report Detail View */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {!selectedReport ? (
            <div className="glass-card" style={{
              padding: '80px 40px',
              textAlign: 'center',
              color: 'var(--text-secondary)'
            }}>
              <FileText size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px', display: 'inline' }} />
              <h3 style={{ fontSize: '1.4rem', color: 'white', marginBottom: '8px' }}>No Run Selected</h3>
              <p>เลือกรายการรันวิเคราะห์ประวัติทางฝั่งซ้ายเพื่อเปิดดูรายงานสรุป DevOps AI</p>
            </div>
          ) : (
            <div className="glass-card" style={{ padding: '30px' }}>
              
              {/* Report Header */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '16px',
                borderBottom: '1px solid var(--glass-border)',
                paddingBottom: '20px',
                marginBottom: '20px'
              }}>
                <div>
                  <h3 style={{ fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span>Analysis Run #{selectedDailyNum || selectedReport.id}</span>
                    <span style={{
                      fontSize: '0.75rem',
                      padding: '4px 10px',
                      borderRadius: '12px',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      background: selectedReport.status === 'success' ? 'rgba(16, 185, 129, 0.15)' : selectedReport.status === 'failed' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(6, 182, 212, 0.15)',
                      color: selectedReport.status === 'success' ? 'var(--color-success)' : selectedReport.status === 'failed' ? 'var(--color-danger)' : 'var(--color-primary)',
                      border: `1px solid ${selectedReport.status === 'success' ? 'rgba(16, 185, 129, 0.3)' : selectedReport.status === 'failed' ? 'rgba(244, 63, 94, 0.3)' : 'rgba(6, 182, 212, 0.3)'}`
                    }}>
                      {selectedReport.status}
                    </span>
                  </h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '6px' }}>
                    <Clock size={14} />
                    <span>{formatDate(selectedReport.timestamp)}</span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {selectedReport.minio_object_name && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', border: '1px dashed var(--glass-border)', borderRadius: '8px', padding: '6px 12px' }}>
                      📦 S3/Minio: {selectedReport.minio_object_name.split('/').pop()}
                    </div>
                  )}
                  <button 
                    onClick={() => handleDeleteReport(selectedReport.id)}
                    className="btn-danger"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 14px',
                      fontSize: '0.85rem',
                      background: 'rgba(244, 63, 94, 0.1)',
                      border: '1px solid rgba(244, 63, 94, 0.3)',
                      color: 'var(--color-danger)',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'rgba(244, 63, 94, 0.2)';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'rgba(244, 63, 94, 0.1)';
                    }}
                  >
                    <Trash2 size={14} />
                    <span>Delete</span>
                  </button>
                </div>
              </div>

              {/* Error Box if Failed */}
              {selectedReport.status === 'failed' && (
                <div style={{
                  background: 'rgba(244, 63, 94, 0.08)',
                  border: '1px solid rgba(244, 63, 94, 0.2)',
                  borderRadius: '10px',
                  padding: '20px',
                  color: 'var(--color-danger)',
                  marginBottom: '20px',
                  display: 'flex',
                  alignItems: 'start',
                  gap: '12px'
                }}>
                  <AlertCircle size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <h4 style={{ fontWeight: 600, marginBottom: '6px' }}>การรันวิเคราะห์ล้มเหลว (Job Execution Failed)</h4>
                    <p style={{ fontSize: '0.9rem', lineHeight: 1.5, opacity: 0.9 }}>{selectedReport.error_message}</p>
                  </div>
                </div>
              )}

              {selectedReport.status === 'running' ? (
                <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-secondary)' }}>
                  <Loader2 className="spin" size={40} style={{ color: 'var(--color-primary)', display: 'inline', animation: 'spin 2s linear infinite', marginBottom: '16px' }} />
                  <h4 style={{ fontSize: '1.2rem', color: 'white', marginBottom: '8px' }}>AI กำลังทำการประมวลผล...</h4>
                  <p style={{ maxWidth: '400px', margin: '0 auto', fontSize: '0.9rem' }}>
                    กำลังดึงประวัติประสิทธิภาพจาก Loki ดึงคิวรีช้าจาก PMM QAN และส่งผลให้ Model วิเคราะห์โครงสร้างคอขวด
                  </p>
                </div>
              ) : (
                <>
                  {/* Tabs */}
                  <div style={{
                    display: 'flex',
                    borderBottom: '1px solid var(--glass-border)',
                    marginBottom: '20px',
                    gap: '10px',
                    flexWrap: 'wrap'
                  }}>
                    <button 
                      onClick={() => setActiveTab('summary')}
                      style={{
                        padding: '12px 20px',
                        background: 'none',
                        border: 'none',
                        borderBottom: activeTab === 'summary' ? '2px solid var(--color-primary)' : '2px solid transparent',
                        color: activeTab === 'summary' ? 'var(--color-primary)' : 'var(--text-secondary)',
                        fontWeight: 600,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}
                    >
                      <FileText size={16} />
                      <span>AI DevOps Report</span>
                    </button>

                    <button 
                      onClick={() => setActiveTab('logs')}
                      style={{
                        padding: '12px 20px',
                        background: 'none',
                        border: 'none',
                        borderBottom: activeTab === 'logs' ? '2px solid var(--color-primary)' : '2px solid transparent',
                        color: activeTab === 'logs' ? 'var(--color-primary)' : 'var(--text-secondary)',
                        fontWeight: 600,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}
                    >
                      <ConsoleIcon size={16} />
                      <span>Nginx Access Logs</span>
                    </button>

                    <button 
                      onClick={() => setActiveTab('queries')}
                      style={{
                        padding: '12px 20px',
                        background: 'none',
                        border: 'none',
                        borderBottom: activeTab === 'queries' ? '2px solid var(--color-primary)' : '2px solid transparent',
                        color: activeTab === 'queries' ? 'var(--color-primary)' : 'var(--text-secondary)',
                        fontWeight: 600,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}
                    >
                      <Database size={16} />
                      <span>PMM QAN Slow SQLs</span>
                    </button>

                    <button 
                      onClick={() => setActiveTab('metrics')}
                      style={{
                        padding: '12px 20px',
                        background: 'none',
                        border: 'none',
                        borderBottom: activeTab === 'metrics' ? '2px solid var(--color-primary)' : '2px solid transparent',
                        color: activeTab === 'metrics' ? 'var(--color-primary)' : 'var(--text-secondary)',
                        fontWeight: 600,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}
                    >
                      <Cpu size={16} />
                      <span>cAdvisor Metrics</span>
                    </button>
                  </div>

                  {/* Tab Contents */}
                  <div className="fade-in" style={{ minHeight: '300px' }}>
                    {activeTab === 'summary' && (
                      <div style={{
                        padding: '10px 0',
                        fontSize: '0.98rem'
                      }}>
                        {renderMarkdown(selectedReport.summary)}
                      </div>
                    )}

                    {activeTab === 'logs' && (
                      <div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '12px' }}>
                          ล็อก NPM/Nginx ที่ถูกคัดเลือกส่งไปให้โมเดลประมวลผล (มี Latency สูง หรือ Status 5xx/Error):
                        </p>
                        <pre style={{
                          background: '#040711',
                          border: '1px solid var(--glass-border)',
                          borderRadius: '10px',
                          padding: '20px',
                          color: '#22d3ee',
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                          overflowX: 'auto',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.5,
                          maxHeight: '500px'
                        }}>
                          {selectedReport.nginx_logs || "ไม่มีประวัติการบันทึก Nginx logs ผิดปกติในช่วงเวลานี้"}
                        </pre>
                      </div>
                    )}

                    {activeTab === 'queries' && (
                      <div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '12px' }}>
                          คำสั่ง SQL ที่บันทึกทำงานช้าที่สุดจาก PostgreSQL Top Queries ดึงจาก PMM:
                        </p>
                        <pre style={{
                          background: '#040711',
                          border: '1px solid var(--glass-border)',
                          borderRadius: '10px',
                          padding: '20px',
                          color: '#a78bfa',
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                          overflowX: 'auto',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.5,
                          maxHeight: '500px'
                        }}>
                          {selectedReport.slow_queries || "ไม่มีประวัติ Slow Queries ในฐานข้อมูลในช่วงเวลานี้"}
                        </pre>
                      </div>
                    )}

                    {activeTab === 'metrics' && (
                      <div>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '12px' }}>
                          ข้อมูลปริมาณการใช้งาน CPU และ Memory ของ Container สำหรับแต่ละโปรเจกต์ ดึงจาก Prometheus (cAdvisor):
                        </p>
                        <pre style={{
                          background: '#040711',
                          border: '1px solid var(--glass-border)',
                          borderRadius: '10px',
                          padding: '20px',
                          color: '#f43f5e',
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                          overflowX: 'auto',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.5,
                          maxHeight: '500px'
                        }}>
                          {selectedReport.prometheus_metrics || "ไม่มีประวัติข้อมูล Resource Metrics ในช่วงเวลานี้"}
                        </pre>
                      </div>
                    )}
                  </div>
                </>
              )}

            </div>
          )}
        </section>

      </div>

      {/* CSS Animation Keyframes Inject */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>

    </div>
  );
}
