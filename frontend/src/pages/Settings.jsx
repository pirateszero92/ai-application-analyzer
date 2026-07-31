import React, { useState, useEffect } from 'react';
import { 
  Save, 
  RefreshCw, 
  Database, 
  Cpu, 
  Clock, 
  Key, 
  Check, 
  AlertCircle,
  Plus,
  X,
  Lock,
  Eye,
  EyeOff,
  MessageSquare
} from 'lucide-react';

export default function Settings({ token, API_BASE }) {
  // System Configurations State
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState({ success: false, error: false, message: '' });

  // Input states (since projects/databases are tags)
  const [lokiProjectInput, setLokiProjectInput] = useState('');
  const [pmmDbInput, setPmmDbInput] = useState('');

  // Password Reveal States
  const [revealPmmPassword, setRevealPmmPassword] = useState(false);

  // Admin Change Password Form State
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwChanging, setPwChanging] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    setFetchError('');
    try {
      const response = await fetch(`${API_BASE}/api/settings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      } else {
        const err = await response.json().catch(() => ({}));
        setFetchError(err.detail || `ไม่สามารถดึงข้อมูลการตั้งค่าได้ (HTTP ${response.status})`);
      }
    } catch (e) {
      console.error("Failed to fetch settings:", e);
      setFetchError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์หลังบ้านได้');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveStatus({ success: false, error: false, message: '' });

    try {
      // Send the update to API
      const response = await fetch(`${API_BASE}/api/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: jsonPayloadBuilder()
      });

      if (response.ok) {
        const updated = await response.json();
        setSettings(updated);
        setSaveStatus({ success: true, error: false, message: 'บันทึกการตั้งค่าระบบเรียบร้อยแล้ว!' });
      } else {
        const err = await response.json();
        setSaveStatus({ success: false, error: true, message: err.detail || 'เกิดข้อผิดพลาดในการบันทึกข้อมูล' });
      }
    } catch (e) {
      setSaveStatus({ success: false, error: true, message: 'ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์หลังบ้านได้' });
    } finally {
      setSaving(false);
      // Clear status after 4 seconds
      setTimeout(() => {
        setSaveStatus({ success: false, error: false, message: '' });
      }, 4000);
    }
  };

  // Helper to build the JSON update payload
  const jsonPayloadBuilder = () => {
    const payload = { ...settings };
    
    // Remove PMM Password from settings state copy if it is empty, or masked
    // (We will let the user type in a separate field if they want to override,
    // or if they just edit the input which holds the PMM password).
    return JSON.stringify(payload);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwError('');
    setPwSuccess('');

    if (newPassword !== confirmPassword) {
      setPwError('รหัสผ่านใหม่และรหัสผ่านยืนยันไม่ตรงกัน');
      return;
    }

    setPwChanging(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword
        })
      });

      if (response.ok) {
        setPwSuccess('เปลี่ยนรหัสผ่านผู้ดูแลระบบเรียบร้อยแล้ว!');
        setOldPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        const err = await response.json();
        setPwError(err.detail || 'รหัสผ่านเดิมไม่ถูกต้อง');
      }
    } catch (e) {
      setPwError('ไม่สามารถเชื่อมต่อระบบเพื่อเปลี่ยนรหัสผ่านได้');
    } finally {
      setPwChanging(false);
    }
  };

  // Tag Manager helpers
  const addLokiProject = () => {
    if (lokiProjectInput.trim() && settings) {
      const projects = [...(settings.loki_projects || [])];
      if (!projects.includes(lokiProjectInput.trim())) {
        projects.push(lokiProjectInput.trim());
        setSettings({ ...settings, loki_projects: projects });
      }
      setLokiProjectInput('');
    }
  };

  const removeLokiProject = (proj) => {
    if (settings) {
      const projects = (settings.loki_projects || []).filter(p => p !== proj);
      setSettings({ ...settings, loki_projects: projects });
    }
  };

  const addPmmDb = () => {
    if (pmmDbInput.trim() && settings) {
      const dbs = [...(settings.pmm_db_filters || [])];
      if (!dbs.includes(pmmDbInput.trim())) {
        dbs.push(pmmDbInput.trim());
        setSettings({ ...settings, pmm_db_filters: dbs });
      }
      setPmmDbInput('');
    }
  };

  const removePmmDb = (dbName) => {
    if (settings) {
      const dbs = (settings.pmm_db_filters || []).filter(d => d !== dbName);
      setSettings({ ...settings, pmm_db_filters: dbs });
    }
  };

  // Helper to dynamically set default host based on provider choice
  const handleProviderChange = (provider) => {
    let host = settings.ai_host_url;
    let model = settings.ai_model_name;
    
    if (provider === 'lmstudio') {
      host = 'http://host.docker.internal:1234/v1';
      model = 'google/gemma-4-e4b';
    } else if (provider === 'ollama') {
      host = 'http://host.docker.internal:11434';
      model = 'gemma2:9b';
    }
    
    setSettings({
      ...settings,
      ai_provider: provider,
      ai_host_url: host,
      ai_model_name: model
    });
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0', color: 'var(--text-secondary)' }}>
        <RefreshCw className="spin" size={32} style={{ display: 'inline', animation: 'spin 2s linear infinite', marginBottom: '16px' }} />
        <p>กำลังโหลดการตั้งค่าระบบ...</p>
      </div>
    );
  }

  if (!settings && fetchError) {
    return (
      <div className="fade-in" style={{ padding: '40px 0', maxWidth: '800px' }}>
        <h2 style={{ fontSize: '2rem', marginBottom: '16px' }}>System Settings</h2>
        <div className="glass-card" style={{ padding: '32px', textAlign: 'center', borderColor: 'rgba(244, 63, 94, 0.3)' }}>
          <AlertCircle size={48} color="var(--color-danger)" style={{ marginBottom: '16px', display: 'inline-block' }} />
          <h3 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>เกิดข้อผิดพลาดในการโหลดการตั้งค่า</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>{fetchError}</p>
          <button onClick={fetchSettings} className="btn-primary" style={{ padding: '10px 24px', display: 'inline-flex', alignItems: 'center', gap: '8px', margin: '0 auto' }}>
            <RefreshCw size={18} />
            <span>ลองใหม่อีกครั้ง</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '30px', maxWidth: '800px' }}>
      
      {/* Title */}
      <div>
        <h2 style={{ fontSize: '2rem', marginBottom: '6px' }}>System Settings</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
          ปรับตั้งค่าการเชื่อมต่อ Monitoring Server, ฐานข้อมูล, AI Engine และผู้ดูแลระบบ
        </p>
      </div>

      {/* Main Form Settings */}
      {settings && (
        <form onSubmit={handleSaveSettings} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Status Alert Banner */}
          {saveStatus.message && (
            <div className="fade-in" style={{
              background: saveStatus.success ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
              border: `1px solid ${saveStatus.success ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              borderRadius: '10px',
              padding: '16px 20px',
              color: saveStatus.success ? 'var(--color-success)' : 'var(--color-danger)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              {saveStatus.success ? <Check size={20} /> : <AlertCircle size={20} />}
              <span style={{ fontSize: '0.95rem', fontWeight: 600 }}>{saveStatus.message}</span>
            </div>
          )}

          {/* Card: Loki */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#38bdf8' }}>
              <Database size={20} />
              <span>1. Grafana Loki (Log Target)</span>
            </h3>

            <div className="form-group">
              <label>Loki Host IP</label>
              <input 
                type="text" 
                className="form-input" 
                value={settings.loki_ip}
                onChange={e => setSettings({ ...settings, loki_ip: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Target Projects (Loki labels)</label>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <input 
                  type="text" 
                  className="form-input" 
                  style={{ flex: 1 }}
                  placeholder="เช่น wms, tms, api-gateway"
                  value={lokiProjectInput}
                  onChange={e => setLokiProjectInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addLokiProject())}
                />
                <button type="button" onClick={addLokiProject} className="btn-secondary" style={{ padding: '0 16px' }}>
                  <Plus size={18} />
                </button>
              </div>

              {/* Tags display */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {(settings.loki_projects || []).map(p => (
                  <span key={p} style={{
                    background: 'rgba(56, 189, 248, 0.1)',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                    color: '#38bdf8',
                    padding: '6px 12px',
                    borderRadius: '20px',
                    fontSize: '0.85rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <span>{p}</span>
                    <button type="button" onClick={() => removeLokiProject(p)} style={{ background: 'none', border: 'none', color: '#38bdf8', display: 'flex' }}>
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Card: PMM */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#c084fc' }}>
              <Database size={20} />
              <span>2. Percona Monitoring (PMM Database Target)</span>
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: '20px' }}>
              <div className="form-group">
                <label>PMM Host IP</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={settings.pmm_ip}
                  onChange={e => setSettings({ ...settings, pmm_ip: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>PMM Port</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={settings.pmm_port}
                  onChange={e => setSettings({ ...settings, pmm_port: e.target.value })}
                  required
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div className="form-group">
                <label>PMM Username</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={settings.pmm_user}
                  onChange={e => setSettings({ ...settings, pmm_user: e.target.value })}
                  required
                />
              </div>
              <div className="form-group" style={{ position: 'relative' }}>
                <label>PMM Password</label>
                <div style={{ display: 'flex', position: 'relative' }}>
                  <input 
                    type={revealPmmPassword ? "text" : "password"} 
                    className="form-input" 
                    style={{ width: '100%', paddingRight: '45px' }}
                    value={settings.pmm_password || ''}
                    onChange={e => setSettings({ ...settings, pmm_password: e.target.value })}
                  />
                  <button 
                    type="button" 
                    onClick={() => setRevealPmmPassword(!revealPmmPassword)}
                    style={{
                      position: 'absolute',
                      right: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      display: 'flex'
                    }}
                  >
                    {revealPmmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
            </div>

            <div className="form-group">
              <label>Database Filters (PMM QAN list)</label>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <input 
                  type="text" 
                  className="form-input" 
                  style={{ flex: 1 }}
                  placeholder="เช่น wms, tms"
                  value={pmmDbInput}
                  onChange={e => setPmmDbInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addPmmDb())}
                />
                <button type="button" onClick={addPmmDb} className="btn-secondary" style={{ padding: '0 16px' }}>
                  <Plus size={18} />
                </button>
              </div>

              {/* Tags display */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {(settings.pmm_db_filters || []).map(d => (
                  <span key={d} style={{
                    background: 'rgba(192, 132, 252, 0.1)',
                    border: '1px solid rgba(192, 132, 252, 0.3)',
                    color: '#c084fc',
                    padding: '6px 12px',
                    borderRadius: '20px',
                    fontSize: '0.85rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <span>{d}</span>
                    <button type="button" onClick={() => removePmmDb(d)} style={{ background: 'none', border: 'none', color: '#c084fc', display: 'flex' }}>
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Card: Prometheus */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#fb7185' }}>
              <Cpu size={20} />
              <span>3. Prometheus / cAdvisor (Infrastructure Metrics)</span>
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div className="form-group">
                <label>Prometheus Host IP</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={settings.prometheus_ip || ''}
                  onChange={e => setSettings({ ...settings, prometheus_ip: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label>Prometheus Port</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={settings.prometheus_port || ''}
                  onChange={e => setSettings({ ...settings, prometheus_port: e.target.value })}
                  required
                />
              </div>
            </div>
          </div>

          {/* Card: AI Model */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#22d3ee' }}>
              <Cpu size={20} />
              <span>4. AI Model Engine Configuration</span>
            </h3>

            <div className="form-group">
              <label>AI Provider</label>
              <select 
                className="form-input" 
                value={settings.ai_provider}
                onChange={e => handleProviderChange(e.target.value)}
                style={{ background: '#0a0f1d' }}
              >
                <option value="lmstudio">LM Studio (OpenAI Compatible)</option>
                <option value="ollama">Ollama (Native/OpenAI Compatible)</option>
                <option value="custom_openai">Custom LLM API / Hermes (OpenAI API Format)</option>
              </select>
            </div>

            <div className="form-group">
              <label>AI API Host URL</label>
              <input 
                type="text" 
                className="form-input" 
                value={settings.ai_host_url}
                onChange={e => setSettings({ ...settings, ai_host_url: e.target.value })}
                required
              />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                * สำหรับการรันบน Docker/K8s เพื่อวิ่งไป Host โลคอล ให้ใช้ <code>http://host.docker.internal:พอร์ต</code>
              </span>
            </div>

            <div className="form-group">
              <label>AI Model Name (ต้องตรงกับโมเดลใน Engine)</label>
              <input 
                type="text" 
                className="form-input" 
                value={settings.ai_model_name}
                onChange={e => setSettings({ ...settings, ai_model_name: e.target.value })}
                required
              />
            </div>
          </div>

          {/* Card: Scheduler */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#fbbf24' }}>
              <Clock size={20} />
              <span>5. Background Scheduler Configuration</span>
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                <div className="form-group">
                  <label>Interval (ความถี่ในการวิเคราะห์อัตโนมัติ - นาที)</label>
                  <input 
                    type="number" 
                    min="5"
                    className="form-input" 
                    value={settings.interval_minutes}
                    onChange={e => setSettings({ ...settings, interval_minutes: parseInt(e.target.value) || 60 })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Lookback Window (วิเคราะห์ข้อมูลย้อนหลัง - นาที)</label>
                  <input 
                    type="number" 
                    min="1"
                    className="form-input" 
                    value={settings.lookback_minutes !== undefined ? settings.lookback_minutes : 15}
                    onChange={e => setSettings({ ...settings, lookback_minutes: parseInt(e.target.value) || 15 })}
                    required
                  />
                </div>
              </div>

              <div className="form-group" style={{ flexDirection: 'row', gap: '12px', alignItems: 'center', marginTop: '10px' }}>
                <input 
                  type="checkbox" 
                  id="scheduler-active"
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                  checked={settings.is_active}
                  onChange={e => setSettings({ ...settings, is_active: e.target.checked })}
                />
                <label htmlFor="scheduler-active" style={{ fontSize: '0.95rem', cursor: 'pointer', userSelect: 'none', color: 'white' }}>
                  เปิดใช้งานตัวรันงานอัตโนมัติ (Scheduler Active)
                </label>
              </div>
            </div>
          </div>

          {/* 6. Discord Notification Integration */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#5865F2' }}>
              <MessageSquare size={20} />
              <span>6. Discord Notification Integration</span>
            </h3>

            <div className="form-group">
              <label>Discord Webhook URL</label>
              <input 
                type="text" 
                placeholder="https://discord.com/api/webhooks/..."
                className="form-input" 
                value={settings.discord_webhook_url || ''}
                onChange={e => setSettings({ ...settings, discord_webhook_url: e.target.value })}
              />
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '6px' }}>
                ลิงก์ Webhook ของช่อง Discord สำหรับส่งรายงานวิเคราะห์ระบบเชิงรุกแบบทันที (Real-time AI Diagnosis) ปล่อยว่างหากต้องการปิดใช้งาน
              </span>
            </div>
          </div>

          {/* 7. Database Configuration Files */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#10b981' }}>
              <Database size={20} />
              <span>7. Database Configuration Files (วิเคราะห์คอนฟิกฐานข้อมูล)</span>
            </h3>
            
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px', lineHeight: '1.4' }}>
              วางข้อความคอนฟิกฐานข้อมูลของคุณ เพื่อให้ AI ใช้ตรวจสอบร่วมกับสถิติประสิทธิภาพจริง และแนะนำวิธีการจูนค่าทรัพยากร (เช่น Connections, Buffer Memory, Security Rules)
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
              <div className="form-group">
                <label>postgresql.conf</label>
                <textarea 
                  placeholder="# วางเนื้อหาไฟล์ postgresql.conf ที่นี่..."
                  className="form-input" 
                  style={{ minHeight: '160px', fontFamily: 'monospace', fontSize: '0.85rem', backgroundColor: '#0d1117', color: '#c9d1d9', resize: 'vertical' }}
                  value={settings.postgresql_conf || ''}
                  onChange={e => setSettings({ ...settings, postgresql_conf: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>pgbouncer.ini</label>
                <textarea 
                  placeholder="# วางเนื้อหาไฟล์ pgbouncer.ini ที่นี่..."
                  className="form-input" 
                  style={{ minHeight: '160px', fontFamily: 'monospace', fontSize: '0.85rem', backgroundColor: '#0d1117', color: '#c9d1d9', resize: 'vertical' }}
                  value={settings.pgbouncer_ini || ''}
                  onChange={e => setSettings({ ...settings, pgbouncer_ini: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>pg_hba.conf</label>
                <textarea 
                  placeholder="# วางเนื้อหาไฟล์ pg_hba.conf ที่นี่..."
                  className="form-input" 
                  style={{ minHeight: '160px', fontFamily: 'monospace', fontSize: '0.85rem', backgroundColor: '#0d1117', color: '#c9d1d9', resize: 'vertical' }}
                  value={settings.pg_hba_conf || ''}
                  onChange={e => setSettings({ ...settings, pg_hba_conf: e.target.value })}
                />
              </div>
            </div>
          </div>

          {/* Card: Server Hardware Specifications — Multi-VM */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px', color: '#a78bfa' }}>
              <Cpu size={20} />
              <span>6. Server Hardware Specifications</span>
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '20px' }}>
              เพิ่ม VM/Server ได้ไม่จำกัด — ข้อมูล Spec ทุก VM จะถูก inject เข้า AI system prompt
              เพื่อให้ AI แนะนำค่าปรับจูนที่สอดคล้องกับทรัพยากรและ architecture จริง เช่น <code style={{ color: '#a78bfa', background: 'rgba(167,139,250,0.1)', padding: '1px 5px', borderRadius: '4px' }}>shared_buffers</code>, <code style={{ color: '#a78bfa', background: 'rgba(167,139,250,0.1)', padding: '1px 5px', borderRadius: '4px' }}>max_connections</code>, <code style={{ color: '#a78bfa', background: 'rgba(167,139,250,0.1)', padding: '1px 5px', borderRadius: '4px' }}>pool_size</code>
            </p>

            {/* VM Cards List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '16px' }}>
              {(settings.server_specs || []).map((vm, idx) => (
                <div key={idx} style={{
                  background: 'rgba(167, 139, 250, 0.05)',
                  border: '1px solid rgba(167, 139, 250, 0.2)',
                  borderRadius: '12px',
                  padding: '18px 20px',
                  position: 'relative'
                }}>
                  {/* VM header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#a78bfa', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Cpu size={15} /> VM #{idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        const updated = (settings.server_specs || []).filter((_, i) => i !== idx);
                        setSettings({ ...settings, server_specs: updated });
                      }}
                      style={{ background: 'none', border: 'none', color: 'var(--color-danger)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem' }}
                    >
                      <X size={14} /> ลบ VM นี้
                    </button>
                  </div>

                  {/* Row 1: Name + Role */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '14px' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>ชื่อ VM / Server Label</label>
                      <input type="text" className="form-input" placeholder="เช่น WMS-DB-01"
                        value={vm.name || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], name: e.target.value };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Role / หน้าที่</label>
                      <select className="form-input" style={{ cursor: 'pointer' }}
                        value={vm.role || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], role: e.target.value };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      >
                        <option value="">-- เลือก Role --</option>
                        <option value="WMS Application Server">WMS Application Server</option>
                        <option value="TMS Application Server">TMS Application Server</option>
                        <option value="WMS Database Server">WMS Database Server (PostgreSQL)</option>
                        <option value="TMS Database Server">TMS Database Server (PostgreSQL)</option>
                        <option value="Shared Database Server">Shared Database Server (WMS+TMS)</option>
                        <option value="Monitoring Server">Monitoring Server (Prometheus/Grafana/Loki)</option>
                        <option value="Proxy / Load Balancer">Proxy / Load Balancer (Nginx)</option>
                        <option value="All-in-One Server">All-in-One Server (App+DB)</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                  </div>

                  {/* Row 2: OS + CPU Model + CPU Cores */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: '16px', marginBottom: '14px' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>OS</label>
                      <input type="text" className="form-input" placeholder="Ubuntu 22.04 LTS"
                        value={vm.os || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], os: e.target.value };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>CPU Model</label>
                      <input type="text" className="form-input" placeholder="Intel Xeon E5-2690 v4"
                        value={vm.cpu_model || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], cpu_model: e.target.value };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>CPU Cores</label>
                      <input type="number" className="form-input" placeholder="16" min="1"
                        value={vm.cpu_cores || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], cpu_cores: e.target.value ? parseInt(e.target.value) : null };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                  </div>

                  {/* Row 3: RAM + Storage Type + Storage Size */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '14px' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>RAM (GB)</label>
                      <input type="number" className="form-input" placeholder="64" min="1"
                        value={vm.ram_gb || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], ram_gb: e.target.value ? parseInt(e.target.value) : null };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Storage Type</label>
                      <select className="form-input" style={{ cursor: 'pointer' }}
                        value={vm.storage_type || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], storage_type: e.target.value };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      >
                        <option value="">-- เลือก --</option>
                        <option value="NVMe SSD">NVMe SSD</option>
                        <option value="SATA SSD">SATA SSD</option>
                        <option value="SAS HDD">SAS HDD</option>
                        <option value="SATA HDD">SATA HDD</option>
                        <option value="Mixed (NVMe+HDD)">NVMe + HDD</option>
                        <option value="Mixed (SSD+HDD)">SSD + HDD</option>
                        <option value="Cloud Storage">Cloud (EBS/GCS)</option>
                      </select>
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Storage Size (GB)</label>
                      <input type="number" className="form-input" placeholder="2048" min="1"
                        value={vm.storage_size_gb || ''}
                        onChange={e => {
                          const updated = [...(settings.server_specs || [])];
                          updated[idx] = { ...updated[idx], storage_size_gb: e.target.value ? parseInt(e.target.value) : null };
                          setSettings({ ...settings, server_specs: updated });
                        }}
                      />
                    </div>
                  </div>

                  {/* Row 4: Notes */}
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label style={{ fontSize: '0.78rem' }}>Notes for AI (ข้อจำกัดพิเศษ / Architecture)</label>
                    <input type="text" className="form-input"
                      placeholder="เช่น Docker บน Proxmox, PostgreSQL ได้ RAM ~48GB, RAID-10"
                      value={vm.notes || ''}
                      onChange={e => {
                        const updated = [...(settings.server_specs || [])];
                        updated[idx] = { ...updated[idx], notes: e.target.value };
                        setSettings({ ...settings, server_specs: updated });
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Add VM Button */}
            <button
              type="button"
              onClick={() => {
                const current = settings.server_specs || [];
                setSettings({
                  ...settings,
                  server_specs: [...current, { name: '', role: '', os: '', cpu_model: '', cpu_cores: null, ram_gb: null, storage_type: '', storage_size_gb: null, notes: '' }]
                });
              }}
              className="btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', borderColor: 'rgba(167,139,250,0.3)', color: '#a78bfa' }}
            >
              <Plus size={16} />
              <span>เพิ่ม VM / Server</span>
            </button>
          </div>

          {/* Card: Direct Database Connections (Diagnostic Engine) */}
          <div className="glass-card" style={{ padding: '24px', marginTop: '16px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px', color: '#10b981' }}>
              <Database size={20} />
              <span>7. Direct Database Connections (Diagnostic SQL Engine)</span>
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '20px' }}>
              ระบุการเชื่อมต่อตรงเข้าสู่ PostgreSQL Instance ของ WMS / TMS ด้วยสิทธิ์ Read-Only เพื่อรันคำสั่ง SQL ดึงข้อมูลลึกระดับ Engine ในแต่ละรอบวิเคราะห์ (เช่น pg_stat_statements, pg_stat_activity, table bloat และ missing index)
            </p>

            {/* DB Connections List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '16px' }}>
              {(settings.db_connections || []).map((conn, idx) => (
                <div key={idx} style={{
                  background: 'rgba(16, 185, 129, 0.03)',
                  border: '1px solid rgba(16, 185, 129, 0.15)',
                  borderRadius: '12px',
                  padding: '18px 20px',
                  position: 'relative'
                }}>
                  {/* Connection header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#10b981', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Database size={15} /> Connection #{idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        const updated = (settings.db_connections || []).filter((_, i) => i !== idx);
                        setSettings({ ...settings, db_connections: updated });
                      }}
                      style={{ background: 'none', border: 'none', color: 'var(--color-danger)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem' }}
                    >
                      <X size={14} /> ลบการเชื่อมต่อนี้
                    </button>
                  </div>

                  {/* Row 1: Label + Host + Port */}
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr', gap: '16px', marginBottom: '14px' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>ชื่อเรียก (Label)</label>
                      <input type="text" className="form-input" placeholder="เช่น WMS-Production-DB"
                        value={conn.label || ''}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], label: e.target.value };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Host / IP Address</label>
                      <input type="text" className="form-input" placeholder="เช่น 10.1.1.24"
                        value={conn.host || ''}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], host: e.target.value };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Port</label>
                      <input type="number" className="form-input" placeholder="5432"
                        value={conn.port || 5432}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], port: e.target.value ? parseInt(e.target.value) : 5432 };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                  </div>

                  {/* Row 2: Database Name + User + Password */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.2fr', gap: '16px', marginBottom: 0 }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Database Name</label>
                      <input type="text" className="form-input" placeholder="เช่น tms"
                        value={conn.dbname || ''}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], dbname: e.target.value };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Username</label>
                      <input type="text" className="form-input" placeholder="เช่น monitor_user"
                        value={conn.user || ''}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], user: e.target.value };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label style={{ fontSize: '0.78rem' }}>Password</label>
                      <input type="password" className="form-input" placeholder="รหัสผ่านเชื่อมต่อ"
                        value={conn.password || ''}
                        onChange={e => {
                          const updated = [...(settings.db_connections || [])];
                          updated[idx] = { ...updated[idx], password: e.target.value };
                          setSettings({ ...settings, db_connections: updated });
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Add Connection Button */}
            <button
              type="button"
              onClick={() => {
                const current = settings.db_connections || [];
                setSettings({
                  ...settings,
                  db_connections: [...current, { label: '', host: '', port: 5432, dbname: '', user: '', password: '' }]
                });
              }}
              className="btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', borderColor: 'rgba(16,185,129,0.3)', color: '#10b981' }}
            >
              <Plus size={16} />
              <span>เพิ่ม Database Connection</span>
            </button>
          </div>

          {/* Card: Proactive Monitoring Settings */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#10b981' }}>
              <Cpu size={20} />
              <span>Proactive AI Monitoring (เฝ้าระวังเชิงรุกตลอด 24 ชม.)</span>
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Enable Switch */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255,255,255,0.02)', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>เปิดใช้งาน Proactive AI Monitor</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    ระบบจะตรวจสุขภาพ WMS/TMS, PgBouncer, DB Connections และ Loki ทุกๆ N นาทีโดยอัตโนมัติ
                  </div>
                </div>
                <input 
                  type="checkbox"
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                  checked={settings.proactive_enabled ?? true}
                  onChange={e => setSettings({ ...settings, proactive_enabled: e.target.checked })}
                />
              </div>

              {/* Interval Selection */}
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Clock size={16} />
                  <span>Proactive Check Interval (ความถี่ในการตรวจสุขภาพ)</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input 
                    type="number" 
                    className="form-input" 
                    style={{ width: '120px' }}
                    min="1"
                    max="60"
                    value={settings.proactive_interval_minutes ?? 2}
                    onChange={e => setSettings({ ...settings, proactive_interval_minutes: parseInt(e.target.value) || 2 })}
                  />
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>นาที (แนะนำ 2-5 นาที)</span>
                </div>
              </div>

              {/* Discord Notification Switch */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255,255,255,0.02)', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>แจ้งเตือนผ่าน Discord เมื่อพบ Anomaly</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    ส่งการวิเคราะห์ Root Cause และคำแนะนำแก้ไขผ่าน Discord Webhook ทันทีเมื่อตรวจพบปัญหา
                  </div>
                </div>
                <input 
                  type="checkbox"
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                  checked={settings.proactive_discord_enabled ?? true}
                  onChange={e => setSettings({ ...settings, proactive_discord_enabled: e.target.checked })}
                />
              </div>
            </div>
          </div>

          {/* Bottom Actions */}
          <button
            type="submit"
            className="btn-primary"
            style={{ padding: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', fontSize: '1rem' }}
            disabled={saving}
          >
            {saving ? (
              <RefreshCw className="spin" size={18} style={{ animation: 'spin 2s linear infinite' }} />
            ) : (
              <Save size={18} />
            )}
            <span>Save Settings</span>
          </button>

        </form>
      )}

      {/* Card: Change Password Administrator */}
      <div className="glass-card" style={{ padding: '24px', marginTop: '10px' }}>
        <h3 style={{ fontSize: '1.2rem', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px', color: '#f43f5e' }}>
          <Key size={20} />
          <span>Change Administrator Password</span>
        </h3>

        <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {pwError && (
            <div className="fade-in" style={{ padding: '10px 16px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: '8px', color: 'var(--color-danger)', fontSize: '0.85rem' }}>
              {pwError}
            </div>
          )}

          {pwSuccess && (
            <div className="fade-in" style={{ padding: '10px 16px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', color: 'var(--color-success)', fontSize: '0.85rem' }}>
              {pwSuccess}
            </div>
          )}

          <div className="form-group">
            <label>Current Password</label>
            <input 
              type="password" 
              className="form-input" 
              value={oldPassword}
              onChange={e => setOldPassword(e.target.value)}
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div className="form-group">
              <label>New Password</label>
              <input 
                type="password" 
                className="form-input" 
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Confirm New Password</label>
              <input 
                type="password" 
                className="form-input" 
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                required
              />
            </div>
          </div>

          <button 
            type="submit" 
            className="btn-secondary" 
            style={{
              padding: '12px',
              color: 'var(--color-danger)',
              borderColor: 'rgba(244, 63, 94, 0.2)',
              background: 'rgba(244, 63, 94, 0.02)',
              fontWeight: 600
            }}
            disabled={pwChanging}
          >
            {pwChanging ? 'Changing Password...' : 'Update Password'}
          </button>
        </form>
      </div>

    </div>
  );
}
