import React, { useState, useEffect } from 'react';
import {
  Calendar,
  RefreshCw,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Activity,
  FileText,
  ChevronRight,
  BarChart2,
  XCircle
} from 'lucide-react';

export default function DailySummary({ token, API_BASE }) {
  const todayStr = new Date().toISOString().split('T')[0];

  // List of available daily summaries (fetched from backend)
  const [summaryList, setSummaryList] = useState([]);
  const [loadingList, setLoadingList] = useState(true);

  // Currently viewed summary
  const [selectedDate, setSelectedDate] = useState(null);
  const [summaryData, setSummaryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Fetch the list of all available daily summaries on mount
  useEffect(() => {
    fetchSummaryList();
  }, []);

  const fetchSummaryList = async () => {
    setLoadingList(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports/daily-summaries`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        // Sort by date descending
        const sorted = [...data].sort((a, b) => b.date.localeCompare(a.date));
        setSummaryList(sorted);
        // Auto-select the most recent
        if (sorted.length > 0 && !selectedDate) {
          selectDate(sorted[0].date);
        }
      }
    } catch (e) {
      console.error('Failed to fetch summary list', e);
    } finally {
      setLoadingList(false);
    }
  };

  const selectDate = async (date, forceRegen = false, shouldGenerate = false) => {
    setSelectedDate(date);
    setLoading(true);
    setError('');
    setSummaryData(null);
    try {
      const response = await fetch(
        `${API_BASE}/api/reports/daily-summary?date=${date}&force=${forceRegen}&generate=${shouldGenerate}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setSummaryData(data);
        // Update the list item if it doesn't exist yet
        setSummaryList(prev => {
          const exists = prev.some(s => s.date === date);
          if (!exists) {
            return [data, ...prev].sort((a, b) => b.date.localeCompare(a.date));
          }
          return prev.map(s => s.date === date ? { ...s, ...data } : s);
        });
      } else {
        const errData = await response.json();
        setError(errData.detail || 'เกิดข้อผิดพลาดในการดึงข้อมูลสรุปประจำวัน');
      }
    } catch (e) {
      console.error(e);
      setError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์หลังบ้านได้');
    } finally {
      setLoading(false);
    }
  };

  const handlePickerDate = (dateStr) => {
    selectDate(dateStr);
  };

  const formatDisplayDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('th-TH', { year: 'numeric', month: '2-digit', day: '2-digit' });
  };

  // Render markdown tags with basic custom regex to look premium
  const renderMarkdown = (text) => {
    if (!text) return <p>ไม่มีสรุปรายงานประจำวัน</p>;
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      if (line.startsWith('### ')) {
        return <h4 key={idx} style={{ color: 'var(--color-primary)', marginTop: '20px', marginBottom: '10px', fontSize: '1.15rem' }}>{line.slice(4)}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} style={{ color: 'var(--color-primary)', marginTop: '24px', marginBottom: '12px', fontSize: '1.3rem', borderBottom: '1px solid var(--glass-border)', paddingBottom: '6px' }}>{line.slice(3)}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={idx} style={{ color: 'white', marginTop: '28px', marginBottom: '16px', fontSize: '1.6rem' }}>{line.slice(2)}</h2>;
      }
      if (line.startsWith('* ') || line.startsWith('- ')) {
        const content = line.slice(2);
        return (
          <li key={idx} style={{ marginLeft: '20px', marginBottom: '8px', color: 'var(--text-primary)', listStyleType: 'square' }}>
            {parseBoldText(content)}
          </li>
        );
      }
      if (line.trim() === '') {
        return <div key={idx} style={{ height: '12px' }} />;
      }
      return <p key={idx} style={{ marginBottom: '10px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>{parseBoldText(line)}</p>;
    });
  };

  const parseBoldText = (text) => {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, i) => {
      if (i % 2 === 1) return <strong key={i} style={{ color: 'white', fontWeight: 700 }}>{part}</strong>;
      return part;
    });
  };

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '2rem', marginBottom: '6px' }}>Daily AI-Ops Summary</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
            วิเคราะห์แนวโน้มปัญหาคอขวดและประสิทธิภาพรายวัน รวบรวมข้อมูลทุก Task เพื่อให้ข้อแนะนำเชิงนโยบาย
          </p>
        </div>

        {/* Date Picker + Re-analyze */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="glass-card" style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '10px', border: '1px solid var(--glass-border)' }}>
            <Calendar size={16} style={{ color: 'var(--color-primary)' }} />
            <input
              type="date"
              defaultValue={todayStr}
              onChange={(e) => handlePickerDate(e.target.value)}
              style={{ background: 'none', border: 'none', color: 'white', outline: 'none', fontFamily: 'monospace', fontSize: '0.95rem', cursor: 'pointer' }}
            />
          </div>
          <button
            onClick={() => selectedDate && selectDate(selectedDate, true, true)}
            disabled={loading || !selectedDate}
            className={`btn-primary ${loading ? 'btn-loading-fill' : ''}`}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px' }}
          >
            {loading ? <Loader2 className="spin" size={15} style={{ animation: 'spin 2s linear infinite' }} /> : <RefreshCw size={15} />}
            <span>Re-analyze</span>
          </button>
        </div>
      </div>

      {/* Main 2-column Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '24px', alignItems: 'start' }}>

        {/* LEFT: Date Panel */}
        <section className="glass-card" style={{
          padding: '20px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          maxHeight: 'calc(100vh - 220px)',
          overflowY: 'auto',
          position: 'sticky',
          top: '20px'
        }}>
          <h3 style={{ fontSize: '1rem', paddingLeft: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Daily Reports</span>
            <button onClick={fetchSummaryList} style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer' }}>
              <RefreshCw size={13} />
            </button>
          </h3>

          {loadingList ? (
            <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--text-muted)' }}>
              <Loader2 size={22} style={{ display: 'inline', animation: 'spin 2s linear infinite', color: 'var(--color-primary)' }} />
              <p style={{ marginTop: '8px', fontSize: '0.85rem' }}>Loading...</p>
            </div>
          ) : summaryList.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)' }}>
              <BarChart2 size={22} style={{ display: 'inline', marginBottom: '8px' }} />
              <p style={{ fontSize: '0.85rem' }}>ยังไม่มีรายงานสรุปรายวัน</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {summaryList.map((s) => {
                const isSelected = selectedDate === s.date;
                const successRate = s.total_runs > 0 ? Math.round((s.success_runs / s.total_runs) * 100) : 0;
                return (
                  <div
                    key={s.date}
                    onClick={() => selectDate(s.date)}
                    className="glass-card"
                    style={{
                      padding: '13px 14px',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(6, 182, 212, 0.1)' : 'rgba(30, 41, 59, 0.2)',
                      borderColor: isSelected ? 'var(--color-primary)' : 'var(--glass-border)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '11px',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    {/* Status dot */}
                    <div style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      flexShrink: 0,
                      background: successRate === 100
                        ? 'var(--color-success)'
                        : successRate >= 50
                          ? 'var(--color-warning, #f59e0b)'
                          : 'var(--color-danger)'
                    }} />

                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: isSelected ? 'var(--color-primary)' : 'white', marginBottom: '3px' }}>
                        {formatDisplayDate(s.date)}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', gap: '8px' }}>
                        <span style={{ color: 'var(--color-success)' }}>✓ {s.success_runs}</span>
                        {s.failed_runs > 0 && <span style={{ color: 'var(--color-danger)' }}>✗ {s.failed_runs}</span>}
                        <span>/ {s.total_runs} runs</span>
                      </div>
                    </div>

                    {isSelected && <ChevronRight size={14} style={{ color: 'var(--color-primary)', flexShrink: 0 }} />}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* RIGHT: Summary Content */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Stats row — only shown when data loaded */}
          {summaryData && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
              <div className="glass-card" style={{ padding: '18px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ background: 'rgba(6, 182, 212, 0.15)', color: 'var(--color-primary)', width: '40px', height: '40px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Activity size={20} />
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>ทั้งหมด</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'white' }}>{summaryData.total_runs} ครั้ง</div>
                </div>
              </div>
              <div className="glass-card" style={{ padding: '18px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-success)', width: '40px', height: '40px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CheckCircle2 size={20} />
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>สำเร็จ</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--color-success)' }}>{summaryData.success_runs} ครั้ง</div>
                </div>
              </div>
              <div className="glass-card" style={{ padding: '18px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ background: 'rgba(244, 63, 94, 0.15)', color: 'var(--color-danger)', width: '40px', height: '40px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <XCircle size={20} />
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>ล้มเหลว</div>
                  <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--color-danger)' }}>{summaryData.failed_runs} ครั้ง</div>
                </div>
              </div>
            </div>
          )}

          {/* Main content card */}
          <div className="glass-card" style={{ padding: '32px', minHeight: '400px', position: 'relative' }}>

            {loading && (
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(10, 15, 29, 0.85)', borderRadius: '16px', zIndex: 5
              }}>
                <Loader2 size={44} style={{ color: 'var(--color-primary)', animation: 'spin 2s linear infinite', marginBottom: '14px' }} />
                <h4 style={{ fontSize: '1.2rem', color: 'white', marginBottom: '6px' }}>AI กำลังจัดทำรายงานสรุปประจำวัน...</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>กำลังประมวลผลรวบรวมข้อมูลทุกรอบการทำงานและตรวจหาแนวโน้มปัญหา</p>
              </div>
            )}

            {!loading && !selectedDate && (
              <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-secondary)' }}>
                <Calendar size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px', display: 'inline' }} />
                <h3 style={{ fontSize: '1.4rem', color: 'white', marginBottom: '8px' }}>เลือกวันที่</h3>
                <p>กรุณาเลือกวันที่ต้องการสรุปผลงานวิเคราะห์จาก panel ทางซ้าย หรือช่องวันที่ด้านบน</p>
              </div>
            )}

            {!loading && error && (
              error.includes('ยังไม่ได้สรุปวิเคราะห์ภาพรวม') ? (
                <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
                  <FileText size={48} style={{ color: 'var(--color-primary)', marginBottom: '16px', display: 'inline' }} />
                  <h3 style={{ fontSize: '1.4rem', color: 'white', marginBottom: '8px' }}>พบประวัติการใช้งานในวันที่ {formatDisplayDate(selectedDate)}</h3>
                  <p style={{ maxWidth: '500px', margin: '0 auto', marginBottom: '24px' }}>
                    พบประวัติการรันวิเคราะห์ในระบบแล้ว แต่ยังไม่ได้ทำการประมวลผลออกรายงานสรุปภาพรวมรายวัน (Daily Summary)
                  </p>
                  <button
                    onClick={() => selectDate(selectedDate, false, true)}
                    disabled={loading}
                    className={`btn-primary ${loading ? 'btn-loading-fill' : ''}`}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 28px', fontSize: '1rem' }}
                  >
                    {loading ? <Loader2 size={18} style={{ animation: 'spin 2s linear infinite' }} /> : <RefreshCw size={18} />}
                    <span>วิเคราะห์สรุปประจำวัน (Generate AI Summary)</span>
                  </button>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
                  <AlertTriangle size={48} style={{ color: 'var(--color-danger)', marginBottom: '16px', display: 'inline' }} />
                  <h3 style={{ fontSize: '1.4rem', color: 'white', marginBottom: '8px' }}>ไม่สามารถดึงข้อมูลได้</h3>
                  <p style={{ maxWidth: '500px', margin: '0 auto' }}>{error}</p>
                </div>
              )
            )}

            {!loading && !error && summaryData && (
              <div>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  borderBottom: '1px solid var(--glass-border)', paddingBottom: '18px', marginBottom: '22px'
                }}>
                  <FileText size={20} style={{ color: 'var(--color-primary)' }} />
                  <h3 style={{ fontSize: '1.35rem', color: 'white' }}>
                    รายงานวิเคราะห์ภาพรวมประจำวันที่ {formatDisplayDate(selectedDate)}
                  </h3>
                </div>
                <div style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>
                  {renderMarkdown(summaryData.summary)}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

    </div>
  );
}
