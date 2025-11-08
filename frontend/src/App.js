import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';

// Public pages
import LandingPage from './pages/LandingPage';
import Registration from './pages/Registration';
import EmailVerificationSent from './pages/EmailVerificationSent';
import OnboardingWizard from './pages/OnboardingWizard';
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
import Guidelines from './pages/Guidelines';
import Settings from './pages/Settings';
import './App.css';

function PrivateRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" />;
}

function App() {
  const [assistantOpen, setAssistantOpen] = useState(false);

  const toggleAssistant = () => {
    setAssistantOpen(!assistantOpen);
  };

  return (
    <Router>
      <div className="app">
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/register" element={<Registration />} />
          <Route path="/verify-email-sent" element={<EmailVerificationSent />} />
          <Route path="/onboarding" element={<OnboardingWizard />} />
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
            path="/guidelines"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Guidelines />
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
