import React, { useState } from 'react';
import './App.css';
import Sidebar from './components/Sidebar';
import Toolbar from './components/Toolbar';
import Dashboard from './components/Dashboard';
import Leads from './components/Leads';
import ActiveLoans from './components/ActiveLoans';
import Portfolio from './components/Portfolio';
import Tasks from './components/Tasks';
import Calendar from './components/Calendar';
import Scorecard from './components/Scorecard';
import AssistantButton from './components/AssistantButton';
import SettingsPage from './pages/SettingsPage';
import RealtorPortal from './pages/RealtorPortal';

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [showAssistant, setShowAssistant] = useState(false);

  const handleViewChange = (view) => {
    switch (view) {
      case 'realtor-portal':
        // If using react-router, navigate('/realtor-portal'); here
        setCurrentView('realtor-portal');
        break;
      default:
        setCurrentView(view);
    }
  };

  const renderView = () => {
    switch (currentView) {
      case 'dashboard':
        return <Dashboard />;
      case 'leads':
        return <Leads />;
      case 'active-loans':
        return <ActiveLoans />;
      case 'portfolio':
        return <Portfolio />;
      case 'tasks':
        return <Tasks />;
      case 'calendar':
        return <Calendar />;
      case 'scorecard':
        return <Scorecard />;
      case 'settings':
        return <SettingsPage />;
      case 'realtor-portal':
        return <RealtorPortal />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="app-container">
      <Sidebar
        currentView={currentView}
        onNavigate={handleViewChange}
      />
      <main className="main-content">
        <Toolbar
          onSettingsClick={() => handleViewChange('settings')}
          onNavigate={handleViewChange}
        />
        <AssistantButton
          onClick={() => setShowAssistant(!showAssistant)}
        />
        {renderView()}
      </main>
    </div>
  );
}
export default App;
