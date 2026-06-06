import { useState } from 'react';
import { useNavigate } from 'react-router-dom'; 
import './LoginPage.css';

interface Feature {
  icon: string;
  label: string;
}

const FEATURES: Feature[] = [
  { icon: '🏪', label: 'Live Sales Dashboards' },
  { icon: '🔒', label: 'Role-Based Access Control' },
  { icon: '📊', label: 'Weekly Data Uploads' },
  { icon: '👥', label: 'All 5 Accra Branches' },
];


const API_URL = import.meta.env.VITE_API_URL;

export default function LoginPage() {
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    setIsLoading(true);
    setMessage(null);

    try {
      const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();
      
      if (response.ok) {
        // Store the access token for future API requests
        localStorage.setItem('access_token', data.access_token);
        
        setMessage({ text: 'Login successful! Redirecting...', type: 'success' });
        
        // Redirect to dashboard after a brief delay
        setTimeout(() => {
          navigate('/dashboard');
        }, 1000);
        
      } else {
        // 
        setMessage({ text: data.detail || 'Invalid email or password.', type: 'error' });
      }
    } catch (error) {
      console.error('Network error:', error);
      setMessage({ text: 'Unable to connect to the server.', type: 'error' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-root">
      {/* ── LEFT PANEL ── */}
      <div className="login-left">
        <div className="left-brand">
          <p className="brand-label">RetailPulse GH</p>
          <h1 className="brand-title">
            Store Performance<br />&amp; Operations Portal
          </h1>
          <p className="brand-tagline">
            Real-time insights for every branch.<br />
            One platform. Five stores. Full control.
          </p>
        </div>

        <div className="left-features">
          {FEATURES.map((f: Feature) => (
            <div className="feature-pill" key={f.label}>
              <span className="feature-icon">{f.icon}</span>
              {f.label}
            </div>
          ))}
        </div>

        <p className="left-footer">Phase 1 · Training Edition</p>
      </div>

      {/* ── RIGHT PANEL ── */}
      <div className="login-right">
        <div className="login-form-wrap">
          <h2 className="form-heading">Welcome back</h2>
          <p className="form-sub">Sign in to access your branch portal</p>

          {message && (
            <div className={`message ${message.type}`}>
              {message.text}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="field-group">
              <label className="field-label" htmlFor="email">Email address</label>
              <input
                id="email"
                className="field-input"
                type="email"
                placeholder="you@retailpulsegh.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="password">Password</label>
              <div className="password-wrap">
                <input
                  id="password"
                  className="field-input"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="show-btn"
                  onClick={() => setShowPassword((prev) => !prev)}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              <a href="/forgot-password" className="forgot-link">Forgot password?</a>
            </div>

            <button type="submit" className="signin-btn" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          <div className="role-notice" role="note">
            <span className="role-icon">🔐</span>
            <div className="role-notice-text">
              <strong>Your role is set automatically</strong>
              <span>
                Store Managers see their branch only.<br />
                Head of Operations sees all 5 branches.
              </span>
            </div>
          </div>
        </div>

        <p className="right-footer">
          © 2024 RetailPulse GH · Powered by Phase 1 Data Engineering Project
        </p>
      </div>
    </div>
  );
}