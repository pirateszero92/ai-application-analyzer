import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Trash2, 
  Loader2, 
  Bot, 
  User, 
  MessageSquare,
  AlertCircle,
  Copy,
  Check,
  X
} from 'lucide-react';

export default function AIChat({ token, API_BASE, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null); // Track copied code blocks

  const chatEndRef = useRef(null);

  const fetchChatHistory = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/chat/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setMessages(data);
      } else {
        setError('ไม่สามารถดึงประวัติการสนทนาได้');
      }
    } catch (e) {
      console.error(e);
      setError('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์หลังบ้านได้');
    } finally {
      setFetching(false);
    }
  };

  useEffect(() => {
    fetchChatHistory();
  }, []);

  const chatBoxRef = useRef(null);

  useEffect(() => {
    // Localized scroll to bottom within chat container (prevents window scrolling)
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const handleSendMessage = async (e) => {
    if (e && typeof e.preventDefault === 'function') {
      e.preventDefault();
    }
    if (!input.trim() || loading) return;

    const userText = input;
    setInput('');
    setLoading(true);
    setError('');

    // Append user message optimistically to the UI
    const tempUserMsg = {
      id: Date.now(),
      role: 'user',
      content: userText,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempUserMsg]);

    try {
      const response = await fetch(`${API_BASE}/api/chat/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ content: userText })
      });

      if (response.ok) {
        const aiMsg = await response.json();
        // Replace user temporary message and add AI message to match server IDs
        setMessages(prev => {
          // Remove the temp user message and replace with official ones to stay in sync
          const filtered = prev.filter(m => m.id !== tempUserMsg.id);
          // Fetch the whole history again to keep DB primary keys in sync!
          return [...filtered, { ...tempUserMsg, id: aiMsg.id - 1 }, aiMsg];
        });
      } else {
        const errData = await response.json();
        setError(errData.detail || 'เกิดข้อผิดพลาดในการรับคำตอบจาก AI');
      }
    } catch (err) {
      console.error(err);
      setError('ไม่สามารถติดต่อเซิร์ฟเวอร์เพื่อสนทนาได้');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm('คุณต้องการล้างประวัติการคุยทั้งหมดกับ AI ใช่หรือไม่? (หน่วความจำระยะยาวของหัวข้อนี้จะถูกล้างออกทั้งหมด)')) {
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat/messages`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setMessages([]);
      } else {
        alert('เกิดข้อผิดพลาดในการล้างข้อมูล');
      }
    } catch (e) {
      console.error(e);
      alert('ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyCode = (codeText, blockIdx) => {
    navigator.clipboard.writeText(codeText);
    setCopiedId(blockIdx);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Format timestamps
  const formatTime = (timeStr) => {
    const d = new Date(timeStr);
    return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
  };

  // Advanced Markdown & Codeblock formatter for AI responses
  const renderAIResponse = (text) => {
    if (!text) return null;

    // Split text by code block markers ```
    const parts = text.split(/(```[\s\S]*?```)/g);

    return parts.map((part, partIdx) => {
      // Check if this part is a code block
      if (part.startsWith('```') && part.endsWith('```')) {
        const match = part.match(/```(\w*)\n([\s\S]*?)```/);
        const language = match ? match[1] : 'code';
        const codeContent = match ? match[2].trim() : part.slice(3, -3).trim();

        return (
          <div 
            key={partIdx} 
            style={{ 
              background: '#090d16', 
              borderRadius: '8px', 
              border: '1px solid var(--glass-border)',
              margin: '12px 0', 
              overflow: 'hidden',
              fontFamily: 'monospace',
              fontSize: '0.9rem'
            }}
          >
            {/* Code Block Header */}
            <div style={{ 
              background: 'rgba(255,255,255,0.02)', 
              padding: '6px 16px', 
              borderBottom: '1px solid var(--glass-border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              color: 'var(--text-secondary)',
              fontSize: '0.78rem'
            }}>
              <span>{language || 'plaintext'}</span>
              <button 
                type="button"
                onClick={() => handleCopyCode(codeContent, partIdx)}
                style={{ 
                  background: 'none', 
                  border: 'none', 
                  color: 'var(--color-primary)', 
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                {copiedId === partIdx ? (
                  <>
                    <Check size={12} style={{ color: 'var(--color-success)' }} />
                    <span style={{ color: 'var(--color-success)' }}>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
            {/* Code Block Content */}
            <pre style={{ margin: 0, padding: '16px', overflowX: 'auto', color: '#e2e8f0', lineHeight: 1.5 }}>
              <code>{codeContent}</code>
            </pre>
          </div>
        );
      }

      // Plain text formatting (headers, bold, lists)
      const lines = part.split('\n');
      return (
        <div key={partIdx} style={{ lineHeight: 1.6 }}>
          {lines.map((line, lineIdx) => {
            // Headers
            if (line.startsWith('### ')) {
              return <h4 key={lineIdx} style={{ color: 'var(--color-primary)', marginTop: '16px', marginBottom: '8px', fontSize: '1.05rem', fontWeight: 600 }}>{line.slice(4)}</h4>;
            }
            if (line.startsWith('## ')) {
              return <h3 key={lineIdx} style={{ color: 'white', marginTop: '20px', marginBottom: '10px', fontSize: '1.2rem', fontWeight: 700 }}>{line.slice(3)}</h3>;
            }
            if (line.startsWith('# ')) {
              return <h2 key={lineIdx} style={{ color: 'white', marginTop: '24px', marginBottom: '12px', fontSize: '1.4rem', fontWeight: 700 }}>{line.slice(2)}</h2>;
            }

            // Bullet Lists
            if (line.startsWith('* ') || line.startsWith('- ')) {
              return (
                <ul key={lineIdx} style={{ margin: '4px 0 4px 20px', paddingLeft: 0, listStyleType: 'disc' }}>
                  <li>{parseInlineMarkdown(line.slice(2))}</li>
                </ul>
              );
            }

            // Numbered Lists
            const numMatch = line.match(/^(\d+)\.\s(.*)/);
            if (numMatch) {
              return (
                <ol key={lineIdx} style={{ margin: '4px 0 4px 20px', paddingLeft: 0 }}>
                  <li value={numMatch[1]}>{parseInlineMarkdown(numMatch[2])}</li>
                </ol>
              );
            }

            // Normal paragraph
            return line.trim() ? (
              <p key={lineIdx} style={{ margin: '8px 0' }}>
                {parseInlineMarkdown(line)}
              </p>
            ) : <div key={lineIdx} style={{ height: '8px' }} />;
          })}
        </div>
      );
    });
  };

  // Helper to parse bold (**text**) and inline code (`code`)
  const parseInlineMarkdown = (text) => {
    // Bold
    let parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, idx) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={idx} style={{ color: 'white', fontWeight: 600 }}>{part.slice(2, -2)}</strong>;
      }
      
      // Inline Code
      let subParts = part.split(/(`.*?`)/g);
      return subParts.map((subPart, subIdx) => {
        if (subPart.startsWith('`') && subPart.endsWith('`')) {
          return (
            <code 
              key={`${idx}-${subIdx}`} 
              style={{ 
                background: 'rgba(255,255,255,0.06)', 
                color: 'var(--color-primary)', 
                padding: '2px 6px', 
                borderRadius: '4px',
                fontFamily: 'monospace',
                fontSize: '0.88rem'
              }}
            >
              {subPart.slice(1, -1)}
            </code>
          );
        }
        return subPart;
      });
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%' }} className="fade-in">
      
      {/* Header Area */}
      <div 
        className="chat-drag-handle"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid var(--glass-border)',
          paddingBottom: '12px',
          background: 'rgba(15, 23, 42, 0.4)',
          padding: '12px 16px',
          borderRadius: '12px 12px 0 0',
          marginBottom: '-12px',
          cursor: 'grab',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={22} style={{ color: 'var(--color-primary)' }} />
          <div>
            <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'white', margin: 0 }}>DevOps AI Assistant</h4>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Context-Aware DB Memory</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClearHistory}
              disabled={loading}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-danger)',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
                opacity: 0.8
              }}
              title="Clear Chat History"
            >
              <Trash2 size={16} />
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--glass-border)',
                color: 'var(--text-secondary)',
                borderRadius: '50%',
                width: '26px',
                height: '26px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                padding: 0
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Main Chat Box Container */}
      <div 
        className="glass-card" 
        style={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column', 
          padding: '24px', 
          overflow: 'hidden',
          background: 'rgba(15, 23, 42, 0.3)',
          border: '1px solid var(--glass-border)'
        }}
      >
        
        {/* Messages Scroll Area */}
        <div 
          ref={chatBoxRef}
          style={{ 
            flex: 1, 
            overflowY: 'auto', 
            paddingRight: '10px', 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '20px',
            marginBottom: '20px'
          }}>
          {fetching ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
              <Loader2 className="spin" size={32} style={{ animation: 'spin 2s linear infinite', marginBottom: '12px' }} />
              <p>กำลังดึงประวัติแชทระยะยาว...</p>
            </div>
          ) : messages.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', textAlign: 'center', padding: '0 20px' }}>
              <MessageSquare size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px', opacity: 0.5 }} />
              <h4 style={{ fontSize: '1.25rem', color: 'white', marginBottom: '8px' }}>เริ่มคุยกับผู้ช่วย DevOps AI</h4>
              <p style={{ maxWidth: '450px', fontSize: '0.9rem', lineHeight: 1.5 }}>
                พิมพ์ถามคำถามเพื่อปรึกษาเกี่ยวกับการตั้งค่าฐานข้อมูล, วิธีจูนคิวรี, หรือหาสาเหตุเออเร่อบน WMS/TMS บอทได้รับการเชื่อมต่อบริบทกับรายงานสถานะล่าสุดของเครื่องคุณเรียบร้อยแล้ว
              </p>
            </div>
          ) : (
            messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div 
                  key={m.id} 
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isUser ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    alignSelf: isUser ? 'flex-end' : 'flex-start',
                    animation: 'fadeIn 0.3s ease-out forwards'
                  }}
                >
                  {/* Sender Name & Badge */}
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px', 
                    marginBottom: '6px',
                    fontSize: '0.78rem',
                    color: 'var(--text-secondary)'
                  }}>
                    {isUser ? (
                      <>
                        <span>User</span>
                        <User size={12} style={{ color: 'var(--color-primary)' }} />
                      </>
                    ) : (
                      <>
                        <Bot size={12} style={{ color: 'var(--color-primary)' }} />
                        <span style={{ color: 'white', fontWeight: 600 }}>DevOps AI</span>
                      </>
                    )}
                  </div>

                  {/* Message Bubble */}
                  <div style={{
                    padding: '14px 18px',
                    borderRadius: '16px',
                    borderTopRightRadius: isUser ? '4px' : '16px',
                    borderTopLeftRadius: isUser ? '16px' : '4px',
                    background: isUser ? 'linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%)' : 'rgba(255, 255, 255, 0.03)',
                    border: isUser ? 'none' : '1px solid var(--glass-border)',
                    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
                    color: isUser ? 'white' : '#cbd5e1',
                    fontSize: '0.98rem',
                    wordBreak: 'break-word'
                  }}>
                    {isUser ? <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{m.content}</p> : renderAIResponse(m.content)}
                  </div>

                  {/* Timestamp */}
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px', padding: '0 4px' }}>
                    {formatTime(m.timestamp)}
                  </span>
                </div>
              );
            })
          )}

          {/* Thinking loading indicator */}
          {loading && (
            <div style={{ display: 'flex', flexDirection: 'column', alignSelf: 'flex-start', animation: 'fadeIn 0.3s ease-out forwards' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                <Bot size={12} style={{ color: 'var(--color-primary)' }} />
                <span>DevOps AI is typing</span>
              </div>
              <div style={{
                padding: '14px 20px',
                borderRadius: '16px',
                borderTopLeftRadius: '4px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid var(--glass-border)',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
              }}>
                <Loader2 className="spin" size={16} style={{ color: 'var(--color-primary)', animation: 'spin 2s linear infinite' }} />
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>กำลังคิดวิเคราะห์คำตอบ...</span>
              </div>
            </div>
          )}

          {error && (
            <div style={{ display: 'flex', gap: '8px', color: 'var(--color-danger)', fontSize: '0.9rem', background: 'rgba(244, 63, 94, 0.1)', padding: '12px 16px', borderRadius: '8px', border: '1px solid rgba(244, 63, 94, 0.2)' }}>
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Text Input Footer Form */}
        <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '12px' }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading || fetching}
            placeholder={loading ? 'กรุณารอ AI ตอบกลับ...' : 'พิมพ์คำถามหรือวาง SQL/Log ที่นี่... (Enter ส่ง / Shift+Enter ขึ้นบรรทัดใหม่)'}
            rows={1}
            style={{
              flex: 1,
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid var(--glass-border)',
              borderRadius: '12px',
              padding: '14px 20px',
              color: 'white',
              fontSize: '1rem',
              outline: 'none',
              transition: 'border-color 0.2s',
              cursor: loading || fetching ? 'not-allowed' : 'text',
              resize: 'vertical',
              minHeight: '52px',
              maxHeight: '180px',
              fontFamily: 'inherit',
              lineHeight: 1.4
            }}
            onFocus={(e) => e.target.style.borderColor = 'var(--color-primary)'}
            onBlur={(e) => e.target.style.borderColor = 'var(--glass-border)'}
          />
          <button
            type="submit"
            disabled={!input.trim() || loading || fetching}
            className={`btn-primary ${loading ? 'btn-loading-fill' : ''}`}
            style={{
              borderRadius: '12px',
              width: '52px',
              height: '52px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
              flexShrink: 0
            }}
          >
            <Send size={18} />
          </button>
        </form>

      </div>
    </div>
  );
}
