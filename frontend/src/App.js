import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';
import OnboardingWizard from './components/OnboardingWizard';

// Public pages
import LandingPage from './pages/LandingPage';
import Registration from './pages/Registration';
import EmailVerificationSent from './pages/EmailVerificationSent';
import Login from './pages/Login';

// Protected pages
import Dashboard from './pages/Dashboard';
import Leads from './pages/Leads';
import LeadDetail from './pages/LeadDetail';
import Loans from './pages/Loans';
import Portfolio from './pages/Portfolio';
import Tasks from './pages/Tasks';
import Calendar from './pages/Calendar';
import Scorecard from './pages/Scorecard';
import Assistant from './pages/Assistant';
import ClientProfile from './pages/ClientProfile';
import ReferralPartners from './pages/ReferralPartners';
import ReferralPartnerDetail from './pages/ReferralPartnerDetail';
import AIUnderwriter from './pages/AIUnderwriter';
import Settings from './pages/Settings';
import './App.css';

function PrivateRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" />;
}

function App() {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);

  const toggleAssistant = () => {
    setAssistantOpen(!assistantOpen);
  };

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
  };

  useEffect(() => {
    const checkOnboardingStatus = async () => {
      if (isAuthenticated()) {
        try {
          const response = await fetch('/api/v1/users/me', {
            headers: {
              'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
          });

          if (response.ok) {
            const userData = await response.json();
            // Show onboarding wizard if user hasn't completed it
            if (!userData.onboarding_completed) {
              setShowOnboarding(true);
            }
          }
        } catch (error) {
          console.error('Error checking onboarding status:', error);
        }
      }
      setCheckingOnboarding(false);
    };

    checkOnboardingStatus();
  }, []);

  return (
    <Router>
      <div className="app">
        {/* Show onboarding wizard overlay for first-time users */}
        {showOnboarding && !checkingOnboarding && (
          <OnboardingWizard onComplete={handleOnboardingComplete} />
        )}

        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/register" element={<Registration />} />
          <Route path="/verify-email-sent" element={<EmailVerificationSent />} />
          <Route path="/login" element={<Login />} />

          {/* Protected routes */}
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Dashboard />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/leads"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Leads />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/leads/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LeadDetail />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/loans"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Loans />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/portfolio"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Portfolio />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Tasks />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Calendar />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/scorecard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Scorecard />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/assistant"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Assistant />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/client/:type/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <ClientProfile />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/referral-partners"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <ReferralPartners />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/referral-partners/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <ReferralPartnerDetail />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/ai-underwriter"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <AIUnderwriter />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Settings />
                  </main>
                  <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
