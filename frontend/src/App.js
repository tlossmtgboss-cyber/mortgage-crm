import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Leads from './pages/Leads';
import Loans from './pages/Loans';
import Portfolio from './pages/Portfolio';
import Tasks from './pages/Tasks';
import Calendar from './pages/Calendar';
import Scorecard from './pages/Scorecard';
import Assistant from './pages/Assistant';
import ClientProfile from './pages/ClientProfile';
import ReferralPartners from './pages/ReferralPartners';
import MUMClients from './pages/MUMClients';
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
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    assistantOpen={assistantOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Routes>
                      <Route path="/" element={<Navigate to="/dashboard" />} />
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/leads" element={<Leads />} />
                      <Route path="/loans" element={<Loans />} />
                      <Route path="/portfolio" element={<Portfolio />} />
                      <Route path="/tasks" element={<Tasks />} />
                      <Route path="/calendar" element={<Calendar />} />
                      <Route path="/scorecard" element={<Scorecard />} />
                      <Route path="/assistant" element={<Assistant />} />
                      <Route path="/client/:type/:id" element={<ClientProfile />} />
                      <Route path="/referral-partners" element={<ReferralPartners />} />
                      <Route path="/mum-clients" element={<MUMClients />} />
                    </Routes>
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
