import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import Navigation from './components/Navigation';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Leads from './pages/Leads';
import Loans from './pages/Loans';
import Tasks from './pages/Tasks';
import Portfolio from './pages/Portfolio';
import Calendar from './pages/Calendar';
import Scorecard from './pages/Scorecard';
import Assistant from './pages/Assistant';
import './App.css';

function PrivateRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" />;
}

function App() {
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
                  <Navigation />
                  <main className="app-main">
                    <Routes>
                      <Route path="/" element={<Navigate to="/dashboard" />} />
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/leads" element={<Leads />} />
                      <Route path="/loans" element={<Loans />} />
                      <Route path="/tasks" element={<Tasks />} />
                              <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/calendar" element={<Calendar />} />
                <Route path="/scorecard" element={<Scorecard />} />
                <Route path="/assistant" element={<Assistant />} />
                    </Routes>
                  </main>
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
