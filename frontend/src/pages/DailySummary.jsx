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
  XCircle,
  Clock,
  Layers,
  Sparkles,
  TrendingUp,
  ShieldCheck,
  HardDrive
} from 'lucide-react';

export default function DailySummary({ token, API_BASE }) {
  const todayStr = new Date().toISOString().split('T')[0];

  // Period mode: 'daily' | 'weekly' | 'monthly'
  const [periodType, setPeriodType] = useState('daily');

  // Daily State
  const [dailyList, setDailyList] = useState([]);
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [dailyData, setDailyData] = useState(null);

  // Weekly & Monthly State
  const [periodicList, setPeriodicList] = useState([]);
  const [selectedPeriodKey, setSelectedPeriodKey] = useState('');
  const [periodicData, setPeriodicData] = useState(null);

  // Retention State
  const [retentionStatus, setRetentionStatus] = useState(null);

  const [loading, setLoading] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [error, setError] = useState('');

  // Initial load
  useEffect(() => {
    fetchRetentionStatus();
    if (periodType === 'daily') {
      fetchDailyList(true);
    } else {
      fetchPeriodicList(periodType, true);
    }
  }, [periodType]);

  const fetchRetentionStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reports/retention-status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setRetentionStatus(data);
      }
    } catch (e) {
      console.error('Failed to fetch retention status', e);
    }
  };

  const fetchDailyList = async (isInitial = false) => {
    if (isInitial) setLoadingList(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports/daily-summaries`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const sorted = [...data].sort((a, b) => b.date.localeCompare(a.date));
        setDailyList(sorted);
        if (sorted.length > 0 && !selectedDate) {
          selectDate(sorted[0].date);
        } else if (selectedDate) {
          selectDate(selectedDate);
        }
      }
    } catch (e) {
      console.error('Failed to fetch daily list', e);
    } finally {
      setLoadingList(false);
    }
  };

  const fetchPeriodicList = async (type, isInitial = false) => {
    if (isInitial) setLoadingList(true);
    try {
      const res = await fetch(`${API_BASE}/api/reports/periodic-summaries?period_type=${type}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setPeriodicList(data);
        if (data.length > 0) {
          selectPeriodic(type, data[0].period_key);
        } else {
          // Default default current week/month
          const defaultKey = type === 'weekly' ? getCurrentWeekKey() : getCurrentMonthKey();
          selectPeriodic(type, defaultKey);
        }
      }
    } catch (e) {
      console.error('Failed to fetch periodic list', e);
    } finally {
      setLoadingList(false);
    }
  };

  const getCurrentWeekKey = () => {
    const d = new Date();
    const target = new Date(d.valueOf());
    const dayNr = (d.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNr + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
    }
    const weekNumber = 1 + Math.ceil((firstThursday - target) / 604800000);
    return `${d.getFullYear()}-W${String(weekNumber).padStart(2, '0')}`;
  };

  const getCurrentMonthKey = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  };

  const selectDate = async (date, forceRegen = false, shouldGenerate = false) => {
    setSelectedDate(date);
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `${API_BASE}/api/reports/daily-summary?date=${date}&force=${forceRegen}&generate=${shouldGenerate}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setDailyData(data);
        setDailyList(prev => {
          const exists = prev.some(s => s.date === date);
          if (!exists) {
            return [data, ...prev].sort((a, b) => b.date.localeCompare(a.date));
          }
          return prev.map(s => s.date === date ? { ...s, ...data } : s);
        });
      } else {
        const errData = await response.json();
        setError(errData.detail || 'เกิดข้อผิดพลาดในการดึงข้อมูลสรุปประจำวัน');
        setDailyData(null);
      }
    } catch (e) {
      console.error(e);
      setError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์หลังบ้านได้');
      setDailyData(null);
    } finally {
      setLoading(false);
    }
  };

  const selectPeriodic = async (type, periodKey, forceRegen = false, shouldGenerate = false) => {
    setSelectedPeriodKey(periodKey);
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `${API_BASE}/api/reports/periodic-summary?period_type=${type}&period_key=${periodKey}&force=${forceRegen}&generate=${shouldGenerate}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setPeriodicData(data);
        setPeriodicList(prev => {
          const exists = prev.some(s => s.period_key === periodKey && s.period_type === type);
          if (!exists) {
            return [data, ...prev];
          }
          return prev.map(s => (s.period_key === periodKey && s.period_type === type) ? { ...s, ...data } : s);
        });
      } else {
        const errData = await response.json();
        setError(errData.detail || `เกิดข้อผิดพลาดในการดึงข้อมูลสรุป ${type}`);
        setPeriodicData(null);
      }
    } catch (e) {
      console.error(e);
      setError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์หลังบ้านได้');
      setPeriodicData(null);
    } finally {
      setLoading(false);
    }
  };

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

  const currentSummaryContent = periodType === 'daily' ? dailyData?.summary : periodicData?.summary;
  const currentTotalRuns = periodType === 'daily' ? dailyData?.total_runs : periodicData?.total_runs;
  const currentSuccessRuns = periodType === 'daily' ? dailyData?.success_runs : periodicData?.success_runs;
  const currentFailedRuns = periodType === 'daily' ? dailyData?.failed_runs : periodicData?.failed_runs;

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* HEADER WITH RETENTION STATUS BADGE */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 700 }}>AI Executive Log & Trend Analyzer</h2>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '20px',
              background: 'rgba(99, 102, 241, 0.15)',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              color: '#818cf8',
              fontSize: '0.75rem',
              fontWeight: 600
            }}>
              <HardDrive size={12} />
              <span>30-DAY LOG ARCHIVE RETENTION (MINIO + PG)</span>
            </div>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            วิเคราะห์ภาพรวมเชิงสถิติ, คอขวดเรื้อรัง, และแผนพัฒนาสถาปัตยกรรม รายวัน (24 ชม.), รายสัปดาห์ (7 วัน), และรายเดือน (30 วัน)
          </p>
        </div>

        {/* PERIOD SELECTOR TABS */}
        <div style={{
          display: 'flex',
          background: 'rgba(15, 23, 42, 0.8)',
          padding: '4px',
          borderRadius: '12px',
          border: '1px solid var(--glass-border)'
        }}>
          <button
            onClick={() => setPeriodType('daily')}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: periodType === 'daily' ? 'var(--color-primary)' : 'transparent',
              color: periodType === 'daily' ? '#0f172a' : 'var(--text-secondary)',
              fontWeight: 700,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Calendar size={14} />
            <span>รายวัน (Daily)</span>
          </button>

          <button
            onClick={() => setPeriodType('weekly')}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: periodType === 'weekly' ? 'var(--color-primary)' : 'transparent',
              color: periodType === 'weekly' ? '#0f172a' : 'var(--text-secondary)',
              fontWeight: 700,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Clock size={14} />
            <span>รายสัปดาห์ (7 วัน)</span>
          </button>

          <button
            onClick={() => setPeriodType('monthly')}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: periodType === 'monthly' ? 'var(--color-primary)' : 'transparent',
              color: periodType === 'monthly' ? '#0f172a' : 'var(--text-secondary)',
              fontWeight: 700,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <BarChart2 size={14} />
            <span>รายเดือน (30 วัน)</span>
          </button>
        </div>
      </div>

      {/* STATS OVERVIEW CARDS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
        
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ padding: '10px', borderRadius: '10px', background: 'rgba(6, 182, 212, 0.1)', color: 'var(--color-primary)' }}>
            <Activity size={20} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Total Analysis Runs</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'white' }}>{currentTotalRuns ?? 0}</div>
          </div>
        </div>

        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ padding: '10px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success)' }}>
            <CheckCircle2 size={20} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Successful Runs</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-success)' }}>{currentSuccessRuns ?? 0}</div>
          </div>
        </div>

        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ padding: '10px', borderRadius: '10px', background: 'rgba(244, 63, 94, 0.1)', color: 'var(--color-danger)' }}>
            <AlertTriangle size={20} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Failed / Incidents</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: (currentFailedRuns || 0) > 0 ? 'var(--color-danger)' : 'white' }}>
              {currentFailedRuns ?? 0}
            </div>
          </div>
        </div>

        {periodType !== 'daily' && (
          <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ padding: '10px', borderRadius: '10px', background: 'rgba(99, 102, 241, 0.1)', color: 'var(--color-secondary)' }}>
              <ShieldCheck size={20} />
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Average Health Score</span>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#818cf8' }}>
                {periodicData?.avg_health_score ? `${periodicData.avg_health_score}/100` : '100/100'}
              </div>
            </div>
          </div>
        )}

      </div>

      {/* MAIN TWO-COLUMN LAYOUT */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '20px', alignItems: 'start' }}>
        
        {/* LEFT COLUMN: NAVIGATION LIST */}
        <div className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'white' }}>
              {periodType === 'daily' ? '📅 เลือกรอบวันที่' : periodType === 'weekly' ? '📆 เลือกรอบสัปดาห์' : '📊 เลือกรอบเดือน'}
            </h4>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {periodType === 'daily' ? `${dailyList.length} วัน` : `${periodicList.length} รอบ`}
            </span>
          </div>

          {/* Quick Date / Week / Month Picker Input */}
          {periodType === 'daily' ? (
            <input 
              type="date" 
              value={selectedDate} 
              max={todayStr}
              onChange={(e) => selectDate(e.target.value)}
              className="glass-card"
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'rgba(0,0,0,0.3)',
                color: 'white',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                fontSize: '0.85rem'
              }}
            />
          ) : periodType === 'weekly' ? (
            <input 
              type="week" 
              value={selectedPeriodKey || getCurrentWeekKey()} 
              onChange={(e) => selectPeriodic('weekly', e.target.value)}
              className="glass-card"
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'rgba(0,0,0,0.3)',
                color: 'white',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                fontSize: '0.85rem'
              }}
            />
          ) : (
            <input 
              type="month" 
              value={selectedPeriodKey || getCurrentMonthKey()} 
              onChange={(e) => selectPeriodic('monthly', e.target.value)}
              className="glass-card"
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'rgba(0,0,0,0.3)',
                color: 'white',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                fontSize: '0.85rem'
              }}
            />
          )}

          {/* Navigation Item List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '420px', overflowY: 'auto' }}>
            {periodType === 'daily' ? (
              dailyList.map(item => {
                const isSel = item.date === selectedDate;
                return (
                  <button
                    key={item.date}
                    onClick={() => selectDate(item.date)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: 'none',
                      background: isSel ? 'rgba(6, 182, 212, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                      color: isSel ? 'var(--color-primary)' : 'var(--text-secondary)',
                      textAlign: 'left',
                      fontSize: '0.85rem',
                      fontWeight: isSel ? 600 : 500,
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      borderLeft: isSel ? '3px solid var(--color-primary)' : '3px solid transparent'
                    }}
                  >
                    <span>{item.date} {item.date === todayStr ? '(วันนี้)' : ''}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.total_runs} runs</span>
                  </button>
                );
              })
            ) : (
              periodicList.map(item => {
                const isSel = item.period_key === selectedPeriodKey;
                return (
                  <button
                    key={item.period_key}
                    onClick={() => selectPeriodic(item.period_type, item.period_key)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: 'none',
                      background: isSel ? 'rgba(6, 182, 212, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                      color: isSel ? 'var(--color-primary)' : 'var(--text-secondary)',
                      textAlign: 'left',
                      fontSize: '0.85rem',
                      fontWeight: isSel ? 600 : 500,
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '2px',
                      borderLeft: isSel ? '3px solid var(--color-primary)' : '3px solid transparent'
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>{item.title || item.period_key}</span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{item.start_date} ถึง {item.end_date}</span>
                  </button>
                );
              })
            )}
          </div>

        </div>

        {/* RIGHT COLUMN: AI REPORT CONTENT */}
        <div className="glass-card" style={{ padding: '28px', minHeight: '520px', display: 'flex', flexDirection: 'column' }}>
          
          {/* Action Toolbar Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'white' }}>
                {periodType === 'daily' 
                  ? `สรุปภาพรวมรายวัน: ${selectedDate || todayStr}` 
                  : periodType === 'weekly' 
                  ? (periodicData?.title || `สรุปภาพรวมสัปดาห์: ${selectedPeriodKey}`)
                  : (periodicData?.title || `สรุปภาพรวมเดือน: ${selectedPeriodKey}`)}
              </h3>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                {periodType === 'daily' ? 'วิเคราะห์บันทึก Logs ย้อนหลัง 24 ชั่วโมง' : 'วิเคราะห์คอขวดและแนวโน้มภาพรวมเชิงสถิติ'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => {
                  if (periodType === 'daily') {
                    selectDate(selectedDate, true, true);
                  } else {
                    selectPeriodic(periodType, selectedPeriodKey, true, true);
                  }
                }}
                disabled={loading}
                className="btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px' }}
              >
                {loading ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
                <span>{currentSummaryContent ? '🤖 สั่ง AI วิเคราะห์ใหม่ (Regenerate)' : '🤖 สั่ง AI สร้างสรุปภาพรวม'}</span>
              </button>
            </div>
          </div>

          {/* Report Body */}
          <div style={{ flex: 1 }}>
            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: '16px' }}>
                <RefreshCw size={36} className="spin" style={{ color: 'var(--color-primary)' }} />
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>AI กำลังรวบรวม Logs ย้อนหลัง, สถิติ Slow Queries และจัดทำรายงานสรุป...</p>
              </div>
            ) : error ? (
              <div style={{
                background: 'rgba(244, 63, 94, 0.08)',
                border: '1px solid rgba(244, 63, 94, 0.2)',
                borderRadius: '12px',
                padding: '24px',
                textAlign: 'center'
              }}>
                <XCircle size={36} style={{ color: 'var(--color-danger)', marginBottom: '10px' }} />
                <h4 style={{ color: 'white', marginBottom: '6px' }}>ยังไม่มีรายงานสรุปในรอบเวลานี้</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '16px' }}>{error}</p>
                <button
                  onClick={() => {
                    if (periodType === 'daily') {
                      selectDate(selectedDate, false, true);
                    } else {
                      selectPeriodic(periodType, selectedPeriodKey, false, true);
                    }
                  }}
                  className="btn-primary"
                  style={{ padding: '8px 18px', fontSize: '0.85rem' }}
                >
                  ✨ สั่ง AI สร้างรายงานตอนนี้เลย
                </button>
              </div>
            ) : currentSummaryContent ? (
              <div style={{ lineHeight: 1.7, color: '#e2e8f0' }}>
                {renderMarkdown(currentSummaryContent)}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
                <FileText size={48} style={{ opacity: 0.5, marginBottom: '12px' }} />
                <p>กดปุ่ม "สั่ง AI สร้างสรุปภาพรวม" ด้านบนเพื่อเริ่มวิเคราะห์รายงาน</p>
              </div>
            )}
          </div>

        </div>

      </div>

    </div>
  );
}
