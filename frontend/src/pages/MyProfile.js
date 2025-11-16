import React, { useState, useEffect } from 'react';
import { getAuth } from '../utils/auth';
import RolesResponsibilitiesTab from '../components/RolesResponsibilitiesTab';
import './MyProfile.css';

/**
 * Employee Self-Service: My Profile Page
 *
 * This page allows employees to view their own:
 * - Job Description (read-only)
 * - Core Responsibilities (read-only)
 * - Goals & OKRs (can submit self-assessments)
 * - Skills Assessment (read-only, shows proficiency levels and gaps)
 *
 * When isManager=false, the RolesResponsibilitiesTab component:
 * - Hides edit/delete buttons for job description and responsibilities
 * - Still allows employees to submit self-assessments for goals
 * - Shows read-only view of skills with gap analysis
 */
function MyProfile() {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const { user } = getAuth();
    if (user) {
      setCurrentUser(user);
    }
    setLoading(false);
  }, []);

  if (loading) {
    return (
      <div className="my-profile-page">
        <div className="loading">Loading your profile...</div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="my-profile-page">
        <div className="error">User not found. Please log in again.</div>
      </div>
    );
  }

  return (
    <div className="my-profile-page">
      <div className="page-header">
        <div className="header-content">
          <h1>My Profile</h1>
          <p className="page-description">
            View your job description, responsibilities, goals, and skills.
            {currentUser.role === 'manager' || currentUser.role === 'management'
              ? ' You can also manage your team in the Team Members section.'
              : ' You can submit self-assessments for your goals below.'}
          </p>
        </div>
        <div className="user-info-card">
          <div className="user-avatar">
            {currentUser.photo_url ? (
              <img src={currentUser.photo_url} alt={currentUser.name} />
            ) : (
              <div className="avatar-initials">
                {currentUser.name?.split(' ').map(n => n[0]).join('') || '?'}
              </div>
            )}
          </div>
          <div className="user-details">
            <h2>{currentUser.name || currentUser.email}</h2>
            <p className="user-role">{currentUser.role || 'Employee'}</p>
            <p className="user-email">{currentUser.email}</p>
          </div>
        </div>
      </div>

      {/* Roles & Responsibilities Tab with Employee View */}
      <div className="profile-content">
        <RolesResponsibilitiesTab
          userId={currentUser.id}
          isManager={false}  // Employee view - limits editing capabilities
        />
      </div>

      {/* Future: Add quick links for common employee tasks */}
      <div className="employee-quick-links">
        <h3>Quick Links</h3>
        <div className="quick-links-grid">
          <a href="#" className="quick-link-card" onClick={(e) => e.preventDefault()}>
            <span className="icon">📋</span>
            <span className="label">My Permissions</span>
            <span className="badge">Coming Soon</span>
          </a>
          <a href="#" className="quick-link-card" onClick={(e) => e.preventDefault()}>
            <span className="icon">🔔</span>
            <span className="label">Notifications</span>
            <span className="badge">Coming Soon</span>
          </a>
          <a href="#" className="quick-link-card" onClick={(e) => e.preventDefault()}>
            <span className="icon">📊</span>
            <span className="label">My Performance</span>
            <span className="badge">Coming Soon</span>
          </a>
        </div>
      </div>
    </div>
  );
}

export default MyProfile;
