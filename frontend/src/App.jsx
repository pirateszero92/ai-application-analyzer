import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  Settings as SettingsIcon, 
  LogOut, 
  Terminal,
  Shield,
  User,
  Lock,
  ChevronRight,
  Calendar,
  MessageSquare
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import DailySummary from './pages/DailySummary';
import AIChat from './pages/AIChat';

// Fallback host for API endpoints (in development, Vite proxies or links to backend port 8000)
// In production, Nginx proxies /api/ to the backend container
const API_BASE = ""; 

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [user, setUser] = useState(null);
  const [activePage, setActivePage] = useState('dashboard');
  const [showChat, setShowChat] = useState(false);
  const [chatPos, setChatPos] = useState({ x: 0, y: 0 });
  const [chatSize, setChatSize] = useState({ width: 420, height: 650 });

  const chatPosRef = useRef({ x: 0, y: 0 });
  const chatSizeRef = useRef({ width: 420, height: 650 });

  const dragStartRef = useRef({ x: 0, y: 0 });
  const isDraggingRef = useRef(false);

  const resizeStartRef = useRef({ width: 0, height: 0, x: 0, y: 0 });
  const isResizingRef = useRef(false);

  const handleMouseDown = (e) => {
    // Ignore dragging when clicking buttons, inputs, textareas, etc.
    if (e.target.closest('button') || e.target.closest('input') || e.target.closest('textarea')) {
      return;
    }
    const isHeaderClick = e.target.closest('.chat-drag-handle');
    if (!isHeaderClick) return;

    isDraggingRef.current = true;
    dragStartRef.current = { 
      x: e.clientX - chatPosRef.current.x, 
      y: e.clientY - chatPosRef.current.y 
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    e.preventDefault();
  };

  const handleMouseMove = (e) => {
    if (!isDraggingRef.current) return;
    const rawX = e.clientX - dragStartRef.current.x;
    const rawY = e.clientY - dragStartRef.current.y;
    
    const defaultLeft = window.innerWidth - 30 - chatSizeRef.current.width;
    const defaultTop = window.innerHeight - 105 - chatSizeRef.current.height;
    
    // Clamp to ensure the window stays in view (at least 100px width and 50px height visible)
    const minX = -defaultLeft;
    const maxX = window.innerWidth - defaultLeft - 100;
    const minY = -defaultTop;
    const maxY = window.innerHeight - defaultTop - 50;
    
    const clampedX = Math.max(minX, Math.min(maxX, rawX));
    const clampedY = Math.max(minY, Math.min(maxY, rawY));
    
    chatPosRef.current = { x: clampedX, y: clampedY };
    setChatPos(chatPosRef.current);
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  };

  const handleResizeMouseDown = (e) => {
    isResizingRef.current = true;
    resizeStartRef.current = { 
      width: chatSizeRef.current.width, 
      height: chatSizeRef.current.height, 
      x: e.clientX, 
      y: e.clientY 
    };
    
    document.addEventListener('mousemove', handleResizeMouseMove);
    document.addEventListener('mouseup', handleResizeMouseUp);
    
    e.preventDefault();
    e.stopPropagation();
  };

  const handleResizeMouseMove = (e) => {
    if (!isResizingRef.current) return;
    const dw = e.clientX - resizeStartRef.current.x;
    const dh = e.clientY - resizeStartRef.current.y;
    
    const newWidth = Math.max(320, Math.min(window.innerWidth - 60, resizeStartRef.current.width + dw));
    const newHeight = Math.max(350, Math.min(window.innerHeight - 100, resizeStartRef.current.height + dh));
    
    chatSizeRef.current = { width: newWidth, height: newHeight };
    setChatSize(chatSizeRef.current);
  };

  const handleResizeMouseUp = () => {
    isResizingRef.current = false;
    document.removeEventListener('mousemove', handleResizeMouseMove);
    document.removeEventListener('mouseup', handleResizeMouseUp);
  };

  // Safe global cleanup on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('mousemove', handleResizeMouseMove);
      document.removeEventListener('mouseup', handleResizeMouseUp);
    };
  }, []);

  const [loginError, setLoginError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  // Check auth status on load
  useEffect(() => {
    if (token) {
      fetchUser();
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        // Token expired or invalid
        handleLogout();
      }
    } catch (e) {
      console.error("Failed to fetch user:", e);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setLoading(true);

    try {
      // OAuth2PasswordRequestForm expects form urlencoded data
      const formData = new URLSearchParams();
      formData.append('username', username);
      formData.append('password', password);

      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('token', data.access_token);
        setToken(data.access_token);
        setUsername('');
        setPassword('');
      } else {
        const errData = await response.json();
        setLoginError(errData.detail || 'Login failed. Please check credentials.');
      }
    } catch (e) {
      setLoginError('Could not connect to API server.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken('');
    setUser(null);
    setActivePage('dashboard');
  };

  // --- LOGIN PAGE ---
  if (!token) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        padding: '20px'
      }}>
        <div className="glass-card fade-in" style={{
          width: '100%',
          maxWidth: '420px',
          padding: '40px 30px',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden'
        }}>
          {/* Logo */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '60px',
            height: '60px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, rgba(6,182,212,0.2) 0%, rgba(99,102,241,0.2) 100%)',
            border: '1px solid var(--color-primary)',
            marginBottom: '20px',
            color: 'var(--color-primary)'
          }}>
            <Terminal size={32} />
          </div>

          <h2 style={{ fontSize: '1.8rem', marginBottom: '8px' }}>AI Log Analyzer</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '30px' }}>
            Automated DevOps Log & Query Analyst
          </p>

          <form onSubmit={handleLogin} style={{ textAlign: 'left' }}>
            {loginError && (
              <div style={{
                background: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.3)',
                borderRadius: '8px',
                padding: '12px',
                color: 'var(--color-danger)',
                fontSize: '0.85rem',
                marginBottom: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <Shield size={16} />
                <span>{loginError}</span>
              </div>
            )}

            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <User size={14} /> Username
              </label>
              <input 
                type="text" 
                className="form-input" 
                placeholder="Enter username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '30px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Lock size={14} /> Password
              </label>
              <input 
                type="password" 
                className="form-input" 
                placeholder="Enter password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <button 
              type="submit" 
              className="btn-primary" 
              style={{ width: '100%', padding: '14px', fontSize: '1rem' }}
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>
          
          <div style={{ marginTop: '24px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Contact your system administrator for access credentials.
          </div>
        </div>
      </div>
    );
  }

  // --- LOGGED IN APPLICATION ---
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      
      {/* SIDEBAR NAVIGATION */}
      <aside className="glass-card" style={{
        width: '260px',
        borderRadius: '0 24px 24px 0',
        borderLeft: 'none',
        borderTop: 'none',
        borderBottom: 'none',
        padding: '30px 20px',
        display: 'flex',
        flexDirection: 'column',
        position: 'fixed',
        top: 0,
        bottom: 0,
        zIndex: 10
      }}>
        {/* Brand */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '40px',
          paddingLeft: '10px'
        }}>
          <div style={{
            background: 'linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%)',
            color: 'white',
            width: '36px',
            height: '36px',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Terminal size={20} />
          </div>
          <div>
            <h1 style={{ fontSize: '1.15rem', fontWeight: 700, lineHeight: 1 }}>AI Log Analyzer</h1>
            <span style={{ fontSize: '0.7rem', color: 'var(--color-primary)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>DevOps Agent</span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
          <button 
            onClick={() => setActivePage('dashboard')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              width: '100%',
              padding: '14px 16px',
              border: 'none',
              borderRadius: '10px',
              background: activePage === 'dashboard' ? 'rgba(6, 182, 212, 0.12)' : 'transparent',
              color: activePage === 'dashboard' ? 'var(--color-primary)' : 'var(--text-secondary)',
              textAlign: 'left',
              fontSize: '0.95rem',
              fontWeight: activePage === 'dashboard' ? 600 : 500,
              borderLeft: activePage === 'dashboard' ? '3px solid var(--color-primary)' : '3px solid transparent'
            }}
          >
            <Activity size={18} />
            <span>Dashboard</span>
            {activePage === 'dashboard' && <ChevronRight size={14} style={{ marginLeft: 'auto' }} />}
          </button>

          <button 
            onClick={() => setActivePage('daily-summary')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              width: '100%',
              padding: '14px 16px',
              border: 'none',
              borderRadius: '10px',
              background: activePage === 'daily-summary' ? 'rgba(6, 182, 212, 0.12)' : 'transparent',
              color: activePage === 'daily-summary' ? 'var(--color-primary)' : 'var(--text-secondary)',
              textAlign: 'left',
              fontSize: '0.95rem',
              fontWeight: activePage === 'daily-summary' ? 600 : 500,
              borderLeft: activePage === 'daily-summary' ? '3px solid var(--color-primary)' : '3px solid transparent'
            }}
          >
            <Calendar size={18} />
            <span>Daily Summary</span>
            {activePage === 'daily-summary' && <ChevronRight size={14} style={{ marginLeft: 'auto' }} />}
          </button>

          <button 
            onClick={() => setActivePage('settings')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              width: '100%',
              padding: '14px 16px',
              border: 'none',
              borderRadius: '10px',
              background: activePage === 'settings' ? 'rgba(6, 182, 212, 0.12)' : 'transparent',
              color: activePage === 'settings' ? 'var(--color-primary)' : 'var(--text-secondary)',
              textAlign: 'left',
              fontSize: '0.95rem',
              fontWeight: activePage === 'settings' ? 600 : 500,
              borderLeft: activePage === 'settings' ? '3px solid var(--color-primary)' : '3px solid transparent'
            }}
          >
            <SettingsIcon size={18} />
            <span>Settings</span>
            {activePage === 'settings' && <ChevronRight size={14} style={{ marginLeft: 'auto' }} />}
          </button>
        </nav>

        {/* User Info & Logout */}
        <div style={{
          borderTop: '1px solid var(--glass-border)',
          paddingTop: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          {user && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '0 8px'
            }}>
              <div style={{
                background: 'rgba(255, 255, 255, 0.05)',
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--glass-border)'
              }}>
                <User size={16} />
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>{user.username}</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Administrator</div>
              </div>
            </div>
          )}

          <button 
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              width: '100%',
              padding: '12px 14px',
              border: '1px solid rgba(244, 63, 94, 0.15)',
              borderRadius: '8px',
              background: 'rgba(244, 63, 94, 0.03)',
              color: 'var(--color-danger)',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* MAIN VIEW CONTENT CONTAINER */}
      <main style={{
        marginLeft: '260px',
        flex: 1,
        padding: '40px',
        minHeight: '100vh',
        maxWidth: 'calc(100% - 260px)'
      }}>
        {activePage === 'dashboard' ? (
          <Dashboard token={token} API_BASE={API_BASE} />
        ) : activePage === 'daily-summary' ? (
          <DailySummary token={token} API_BASE={API_BASE} />
        ) : (
          <Settings token={token} API_BASE={API_BASE} />
        )}
      </main>

      {/* FLOATING CHAT TRIGGER BUTTON */}
      <button 
        onClick={() => setShowChat(!showChat)}
        style={{
          position: 'fixed',
          bottom: '30px',
          right: '30px',
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%)',
          color: 'white',
          border: 'none',
          cursor: 'pointer',
          boxShadow: '0 8px 32px rgba(6, 182, 212, 0.35)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          transition: 'transform 0.2s'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.08)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
        title="Chat with AI DevOps Assistant"
      >
        <MessageSquare size={26} />
      </button>

      {/* FLOATING CHAT WINDOW */}
      {showChat && (
        <div 
          className="glass-card"
          onMouseDown={handleMouseDown}
          style={{
            position: 'fixed',
            bottom: '105px',
            right: '30px',
            width: `${chatSize.width}px`,
            height: `${chatSize.height}px`,
            maxWidth: 'calc(100vw - 60px)',
            maxHeight: 'calc(100vh - 145px)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            padding: '16px',
            boxShadow: '0 20px 50px rgba(0, 0, 0, 0.4)',
            background: 'rgba(15, 23, 42, 0.95)',
            backdropFilter: 'blur(20px)',
            borderColor: 'var(--color-primary)',
            transform: `translate(${chatPos.x}px, ${chatPos.y}px)`,
            transition: isDraggingRef.current || isResizingRef.current ? 'none' : 'transform 0.05s ease-out'
          }}
        >
          <AIChat token={token} API_BASE={API_BASE} onClose={() => setShowChat(false)} />

          {/* RESIZE HANDLE */}
          <div 
            onMouseDown={handleResizeMouseDown}
            style={{
              position: 'absolute',
              right: '4px',
              bottom: '4px',
              width: '14px',
              height: '14px',
              cursor: 'se-resize',
              zIndex: 1002,
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'flex-end',
              opacity: 0.6
            }}
            title="Drag to Resize"
          >
            <svg width="8" height="8" viewBox="0 0 8 8">
              <line x1="6" y1="0" x2="0" y2="6" stroke="var(--color-primary)" strokeWidth="1.5" />
              <line x1="8" y1="2" x2="2" y2="8" stroke="var(--color-primary)" strokeWidth="1.5" />
            </svg>
          </div>
        </div>
      )}

    </div>
  );
}
