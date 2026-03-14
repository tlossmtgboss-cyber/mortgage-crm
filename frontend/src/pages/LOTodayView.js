import React from 'react';
import { Link } from 'react-router-dom';
import {
  getGreeting,
  formatFullDate,
  getUserName,
  SectionErrorBoundary,
  ScheduleSection,
  TasksSection,
  LeadFollowUpSection,
  SLASection,
} from './lo-today';
import './LOTodayView.css';

// =============================================================================
// Main Component
// =============================================================================

export default function LOTodayView() {
  const now = new Date();
  const userName = getUserName();
  const greeting = getGreeting();

  return (
    <div className="lo-today">
      {/* Header */}
      <div className="lo-today__header">
        <h1 className="lo-today__greeting">
          {greeting}{userName ? `, ${userName}` : ''}
        </h1>
        <p className="lo-today__date">{formatFullDate(now)}</p>
        <div className="lo-today__quick-links">
          <Link to="/calendar" className="lo-today__quick-link">
            Calendar
          </Link>
          <Link to="/pipeline-efficiency" className="lo-today__quick-link">
            Pipeline
          </Link>
          <Link to="/leads" className="lo-today__quick-link">
            Leads
          </Link>
          <Link to="/tasks" className="lo-today__quick-link">
            Tasks
          </Link>
          <Link to="/calendar/analytics" className="lo-today__quick-link">
            Analytics
          </Link>
        </div>
      </div>

      {/* 2x2 Grid */}
      <div className="lo-today__grid">
        <SectionErrorBoundary sectionName="schedule">
          <ScheduleSection />
        </SectionErrorBoundary>

        <SectionErrorBoundary sectionName="tasks">
          <TasksSection />
        </SectionErrorBoundary>

        <SectionErrorBoundary sectionName="leads">
          <LeadFollowUpSection />
        </SectionErrorBoundary>

        <SectionErrorBoundary sectionName="sla">
          <SLASection />
        </SectionErrorBoundary>
      </div>
    </div>
  );
}
