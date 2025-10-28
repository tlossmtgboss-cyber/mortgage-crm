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

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [showAssistant, setShowAssistant] = useState(false);

  const renderView = () => {
    switch(currentView) {
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
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="app-container">
      <Sidebar 
        currentView={currentView} 
        onNavigate={setCurrentView} 
      />
      <main className="main-content">
        <Toolbar onSettingsClick={() => setCurrentView('settings')} />
        <AssistantButton 
          onClick={() => setShowAssistant(!showAssistant)} 
        />
        {renderView()}
      </main>
    </div>
  );
}

export default App;
