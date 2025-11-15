import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import './LandingPage.css';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname.includes('vercel.app');
const API_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function LandingPage() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPlans();
  }, []);

  const loadPlans = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/plans`);
      setPlans(response.data.plans);
    } catch (error) {
      console.error('Failed to load plans:', error);
      // Use fallback plans if API fails
      setPlans([
        {
          key: 'professional',
          name: 'Professional',
          price_monthly: 199,
          features: [
            'Up to 15 team members',
            'Unlimited leads',
            'Advanced AI assistant',
            'Priority support'
          ]
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleGetStarted = (planKey = 'professional') => {
    navigate(`/register?plan=${planKey}`);
  };

  return (
    <div className="landing-page">
      {/* Navigation Bar */}
      <nav className="landing-nav">
        <div className="landing-nav-container">
          <div className="landing-logo">
            <span className="logo-icon">🏠</span>
            <span className="logo-text">Mortgage CRM</span>
          </div>
          <div className="landing-nav-actions">
            <button className="btn-login" onClick={() => navigate('/login')}>
              Log In
            </button>
            <button className="btn-signup" onClick={() => handleGetStarted('professional')}>
              Sign Up
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-content">
          <h1 className="hero-title">
            AI-Powered Mortgage CRM
          </h1>
          <p className="hero-subtitle">
            Transform your mortgage business with intelligent automation,
            seamless integrations, and data-driven insights
          </p>
          <div className="hero-cta">
            <button
              className="btn-primary-large"
              onClick={() => handleGetStarted('professional')}
            >
              Start Free Trial
            </button>
            <button
              className="btn-secondary-large"
              onClick={() => document.getElementById('features').scrollIntoView({ behavior: 'smooth' })}
            >
              Learn More
            </button>
          </div>
          <p className="hero-note">14-day free trial • No credit card required</p>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="features-section">
        <h2>Everything You Need to Scale Your Business</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">🤖</div>
            <h3>AI Assistant</h3>
            <p>Intelligent copilot that automates tasks, prioritizes leads, and provides actionable insights</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">📊</div>
            <h3>Pipeline Management</h3>
            <p>Track leads from first contact to funded loan with automated status updates</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🔗</div>
            <h3>Seamless Integrations</h3>
            <p>Connect with Microsoft Teams, Outlook, SMS, and calendar for unified communication</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">⚡</div>
            <h3>Task Automation</h3>
            <p>AI-driven task creation and assignment based on pipeline triggers and deadlines</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">📧</div>
            <h3>Email Intelligence</h3>
            <p>Automatically parse emails to update CRM status and create follow-up tasks</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">📈</div>
            <h3>Advanced Analytics</h3>
            <p>Comprehensive scorecards, conversion metrics, and performance tracking</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">💬</div>
            <h3>SMS & Notifications</h3>
            <p>Automated text messages for client updates, reminders, and status changes</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🎯</div>
            <h3>Custom Workflows</h3>
            <p>AI generates workflows tailored to your team structure and processes</p>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="pricing-section">
        <h2>Simple, Transparent Pricing</h2>
        <p className="pricing-subtitle">Choose the plan that fits your business</p>

        {loading ? (
          <div className="loading">Loading plans...</div>
        ) : (
          <div className="pricing-grid">
            {plans.map((plan) => (
              <div key={plan.key} className={`pricing-card ${plan.key === 'professional' ? 'featured' : ''}`}>
                {plan.key === 'professional' && <div className="popular-badge">Most Popular</div>}

                <h3 className="plan-name">{plan.name}</h3>
                <div className="plan-price">
                  <span className="price-amount">${plan.price_monthly}</span>
                  <span className="price-period">/month</span>
                </div>

                <ul className="plan-features">
                  {plan.features.map((feature, index) => (
                    <li key={index}>
                      <span className="feature-check">✓</span>
                      {feature}
                    </li>
                  ))}
                </ul>

                <button
                  className={`btn-plan ${plan.key === 'professional' ? 'btn-plan-featured' : ''}`}
                  onClick={() => handleGetStarted(plan.key)}
                >
                  Get Started
                </button>

                <p className="plan-trial">14-day free trial included</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Testimonials Section */}
      <section className="testimonials-section">
        <h2>Trusted by Top Mortgage Professionals</h2>
        <div className="testimonials-grid">
          <div className="testimonial-card">
            <p className="testimonial-text">
              "This CRM has completely transformed how we manage our pipeline. The AI assistant saves us 10+ hours per week on administrative tasks."
            </p>
            <div className="testimonial-author">
              <strong>Sarah Johnson</strong>
              <span>Senior Loan Officer, ABC Lending</span>
            </div>
          </div>

          <div className="testimonial-card">
            <p className="testimonial-text">
              "The email intelligence feature is a game-changer. No more manual data entry - everything updates automatically."
            </p>
            <div className="testimonial-author">
              <strong>Michael Chen</strong>
              <span>Branch Manager, XYZ Mortgage</span>
            </div>
          </div>

          <div className="testimonial-card">
            <p className="testimonial-text">
              "We've seen a 40% increase in conversion rates since implementing this system. The analytics are incredibly powerful."
            </p>
            <div className="testimonial-author">
              <strong>Emily Davis</strong>
              <span>Regional Director, Premier Home Loans</span>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <h2>Ready to Transform Your Business?</h2>
        <p>Join hundreds of mortgage professionals using AI to close more loans</p>
        <button
          className="btn-primary-large"
          onClick={() => handleGetStarted('professional')}
        >
          Start Your Free Trial
        </button>
        <p className="cta-note">No credit card required • Setup in minutes</p>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="footer-content">
          <div className="footer-section">
            <h4>Mortgage CRM</h4>
            <p>AI-powered CRM for mortgage professionals</p>
          </div>
          <div className="footer-section">
            <h4>Product</h4>
            <ul>
              <li>Features</li>
              <li>Pricing</li>
              <li>Integrations</li>
              <li>Security</li>
            </ul>
          </div>
          <div className="footer-section">
            <h4>Support</h4>
            <ul>
              <li>Documentation</li>
              <li>Help Center</li>
              <li>Contact Us</li>
            </ul>
          </div>
          <div className="footer-section">
            <h4>Company</h4>
            <ul>
              <li>About</li>
              <li>Blog</li>
              <li>Privacy Policy</li>
              <li>Terms of Service</li>
            </ul>
          </div>
        </div>
        <div className="footer-bottom">
          <p>© 2025 Mortgage CRM. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

export default LandingPage;
