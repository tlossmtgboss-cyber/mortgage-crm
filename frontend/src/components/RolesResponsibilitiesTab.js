import React, { useState } from 'react';
import JobDescriptionSection from './JobDescriptionSection';
import './RolesResponsibilitiesTab.css';

/**
 * Tab 2: Roles & Responsibilities
 *
 * Four main sections:
 * 1. Job Description - Rich text editor for comprehensive role description
 * 2. Core Responsibilities - CRUD for managing responsibilities with time allocation
 * 3. Goals & OKRs - Objective and Key Results tracking with self/manager assessment
 * 4. Skills Assessment - Proficiency tracking with gap analysis
 */

function RolesResponsibilitiesTab({ userId }) {
  const [activeSection, setActiveSection] = useState('job-description');

  return (
    <div className="roles-responsibilities-tab">
      <div className="section-header">
        <h2>Roles & Responsibilities</h2>
        <p className="section-description">
          Manage job descriptions, responsibilities, goals, and skills assessment
        </p>
      </div>

      {/* Sub-navigation for sections */}
      <div className="section-tabs">
        <button
          className={`section-tab-btn ${activeSection === 'job-description' ? 'active' : ''}`}
          onClick={() => setActiveSection('job-description')}
        >
          Job Description
        </button>
        <button
          className={`section-tab-btn ${activeSection === 'responsibilities' ? 'active' : ''}`}
          onClick={() => setActiveSection('responsibilities')}
        >
          Core Responsibilities
        </button>
        <button
          className={`section-tab-btn ${activeSection === 'goals' ? 'active' : ''}`}
          onClick={() => setActiveSection('goals')}
        >
          Goals & OKRs
        </button>
        <button
          className={`section-tab-btn ${activeSection === 'skills' ? 'active' : ''}`}
          onClick={() => setActiveSection('skills')}
        >
          Skills Assessment
        </button>
      </div>

      {/* Section Content */}
      <div className="section-content">
        {activeSection === 'job-description' && (
          <JobDescriptionSection userId={userId} />
        )}

        {activeSection === 'responsibilities' && (
          <div className="placeholder-section">
            <h3>Core Responsibilities</h3>
            <p>CRUD interface for managing responsibilities - Coming soon...</p>
            <div className="placeholder-features">
              <ul>
                <li>Add/edit/archive responsibilities</li>
                <li>Drag-and-drop reordering</li>
                <li>Time allocation tracking (with warning if &gt;100%)</li>
                <li>Priority levels (Critical/High/Medium/Low)</li>
                <li>Required skills mapping</li>
                <li>Effective date ranges</li>
              </ul>
            </div>
          </div>
        )}

        {activeSection === 'goals' && (
          <div className="placeholder-section">
            <h3>Goals & OKRs</h3>
            <p>Objective and Key Results tracking - Coming soon...</p>
            <div className="placeholder-features">
              <ul>
                <li>Create objectives with measurable key results</li>
                <li>Progress tracking with visual indicators</li>
                <li>Employee self-assessment</li>
                <li>Manager assessment and feedback</li>
                <li>Quarterly goal filtering</li>
                <li>Link goals to responsibilities</li>
              </ul>
            </div>
          </div>
        )}

        {activeSection === 'skills' && (
          <div className="placeholder-section">
            <h3>Skills Assessment</h3>
            <p>Proficiency tracking and gap analysis - Coming soon...</p>
            <div className="placeholder-features">
              <ul>
                <li>Skills matrix with required vs. current proficiency</li>
                <li>Gap analysis (5-star rating system)</li>
                <li>Training recommendations</li>
                <li>Assessment history and trends</li>
                <li>Next assessment date tracking</li>
                <li>Skills library management</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default RolesResponsibilitiesTab;
