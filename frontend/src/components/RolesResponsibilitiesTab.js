import React, { useState } from 'react';
import JobDescriptionSection from './JobDescriptionSection';
import CoreResponsibilitiesSection from './CoreResponsibilitiesSection';
import GoalsOKRsSection from './GoalsOKRsSection';
import SkillsAssessmentSection from './SkillsAssessmentSection';
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

function RolesResponsibilitiesTab({ userId, isManager = true }) {
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
          <CoreResponsibilitiesSection userId={userId} />
        )}

        {activeSection === 'goals' && (
          <GoalsOKRsSection userId={userId} isManager={isManager} />
        )}

        {activeSection === 'skills' && (
          <SkillsAssessmentSection userId={userId} isManager={isManager} />
        )}
      </div>
    </div>
  );
}

export default RolesResponsibilitiesTab;
