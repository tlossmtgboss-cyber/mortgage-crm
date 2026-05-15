/**
 * Marketing Tab
 *
 * Displays borrower story elements captured by the Marketing Agent:
 * - Story themes (first-time buyer, growing family, etc.)
 * - Emotional moments and milestones
 * - Quotable moments for testimonials
 * - Content ideas for social posts and marketing
 *
 * Every customer has a story - this tab captures it for later celebration.
 */

import React, { useState } from 'react';

const MarketingTab = ({
  storyNotes = [],
  storyThemes = [],
  borrowerQuotes = [],
  contentIdeas = [],
  milestones = [],
  borrowerName = '',
}) => {
  const [expandedQuote, setExpandedQuote] = useState(null);

  // Get the primary story theme
  const primaryTheme = storyThemes[0]?.structured_data?.story_theme || null;

  // Get story arc position
  const storyArcPosition = storyThemes[0]?.structured_data?.story_arc_position || 'beginning';

  // Format milestone type
  const formatMilestone = (type) => {
    const milestoneLabels = {
      first_call: 'First Contact',
      pre_approval: 'Pre-Approval',
      offer_accepted: 'Offer Accepted',
      clear_to_close: 'Clear to Close',
      closing: 'Closing Day!',
    };
    return milestoneLabels[type] || type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '';
  };

  // Get emotion badge color
  const getEmotionColor = (emotion) => {
    const colors = {
      excitement: '#2D7A52',
      gratitude: '#B8924A',
      determination: '#f59e0b',
      hope: '#3b82f6',
      relief: '#06b6d4',
      joy: '#ec4899',
    };
    return colors[emotion] || '#6b7280';
  };

  // Get marketing potential badge
  const getMarketingPotentialBadge = (potential) => {
    if (potential === 'high') return <span className="badge badge-green">High Potential</span>;
    if (potential === 'medium') return <span className="badge badge-yellow">Medium</span>;
    return null;
  };

  const hasContent = storyNotes.length > 0 || storyThemes.length > 0 ||
    borrowerQuotes.length > 0 || contentIdeas.length > 0 || milestones.length > 0;

  if (!hasContent) {
    return (
      <div className="marketing-tab marketing-tab-empty">
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h3>Story in Progress</h3>
          <p>As you talk with the borrower, their story will be captured here for future marketing and celebration content.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="marketing-tab">
      {/* Story Theme Header */}
      {primaryTheme && (
        <div className="story-header">
          <div className="story-theme-badge">
            <span className="theme-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </span>
            <div className="theme-content">
              <span className="theme-label">Story Theme</span>
              <span className="theme-value">{primaryTheme}</span>
            </div>
          </div>
          <div className="story-arc">
            <span className="arc-label">Journey Stage:</span>
            <div className="arc-progress">
              <div className={`arc-dot ${storyArcPosition === 'beginning' ? 'active' : ''}`} title="Beginning"></div>
              <div className="arc-line"></div>
              <div className={`arc-dot ${storyArcPosition === 'building' ? 'active' : ''}`} title="Building"></div>
              <div className="arc-line"></div>
              <div className={`arc-dot ${storyArcPosition === 'climax' ? 'active' : ''}`} title="Climax"></div>
              <div className="arc-line"></div>
              <div className={`arc-dot ${storyArcPosition === 'resolution' ? 'active' : ''}`} title="Resolution"></div>
            </div>
          </div>
        </div>
      )}

      {/* Why They're Buying */}
      {storyThemes[0]?.structured_data?.why_buying && (
        <div className="why-buying-card">
          <h4>Why They're Buying</h4>
          <p>{storyThemes[0].structured_data.why_buying}</p>
          {storyThemes[0].structured_data.family_situation && (
            <div className="family-situation">
              <span className="label">Family:</span>
              <span className="value">{storyThemes[0].structured_data.family_situation}</span>
            </div>
          )}
          {storyThemes[0].structured_data.dreams_for_home && (
            <div className="dreams">
              <span className="label">Dream:</span>
              <span className="value">{storyThemes[0].structured_data.dreams_for_home}</span>
            </div>
          )}
        </div>
      )}

      {/* Milestones */}
      {milestones.length > 0 && (
        <div className="marketing-section">
          <h4>Journey Milestones</h4>
          <div className="milestones-list">
            {milestones.map((milestone, index) => (
              <div key={index} className="milestone-card">
                <div className="milestone-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22,4 12,14.01 9,11.01" />
                  </svg>
                </div>
                <div className="milestone-content">
                  <span className="milestone-type">{formatMilestone(milestone.structured_data?.milestone_type)}</span>
                  <p className="milestone-significance">{milestone.structured_data?.significance || milestone.content}</p>
                  {milestone.structured_data?.celebration_note && (
                    <span className="celebration-note">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                        <circle cx="12" cy="12" r="10" />
                        <path d="M8 14s1.5 2 4 2 4-2 4-2" />
                        <line x1="9" y1="9" x2="9.01" y2="9" />
                        <line x1="15" y1="9" x2="15.01" y2="9" />
                      </svg>
                      {milestone.structured_data.celebration_note}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quotable Moments */}
      {borrowerQuotes.length > 0 && (
        <div className="marketing-section">
          <h4>Quotable Moments</h4>
          <div className="quotes-list">
            {borrowerQuotes.map((quote, index) => (
              <div
                key={index}
                className={`quote-card ${expandedQuote === index ? 'expanded' : ''}`}
                onClick={() => setExpandedQuote(expandedQuote === index ? null : index)}
              >
                <div className="quote-icon">"</div>
                <blockquote>{quote.content}</blockquote>
                {quote.structured_data?.context && expandedQuote === index && (
                  <div className="quote-context">
                    <span className="context-label">Context:</span>
                    <span className="context-value">{quote.structured_data.context}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Story Notes */}
      {storyNotes.length > 0 && (
        <div className="marketing-section">
          <h4>Story Elements</h4>
          <div className="story-notes-list">
            {storyNotes.map((note, index) => (
              <div key={index} className="story-note-card">
                <div className="note-header">
                  <span
                    className="emotion-badge"
                    style={{ backgroundColor: getEmotionColor(note.structured_data?.emotion) }}
                  >
                    {note.structured_data?.emotion || 'moment'}
                  </span>
                  {getMarketingPotentialBadge(note.structured_data?.marketing_potential)}
                </div>
                <p className="note-content">{note.content}</p>
                {note.structured_data?.context && (
                  <span className="note-context">{note.structured_data.context}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Content Ideas */}
      {contentIdeas.length > 0 && (
        <div className="marketing-section">
          <h4>Content Ideas</h4>
          <div className="content-ideas-list">
            {contentIdeas.map((idea, index) => (
              <div key={index} className="content-idea-card">
                <div className="idea-type">
                  <span className={`type-badge type-${idea.structured_data?.content_type || 'general'}`}>
                    {(idea.structured_data?.content_type || 'content').replace(/_/g, ' ')}
                  </span>
                </div>
                <h5>{idea.title?.replace('Content Idea: ', '') || 'Content Idea'}</h5>
                <p>{idea.structured_data?.concept || idea.content}</p>
                {idea.structured_data?.key_elements?.length > 0 && (
                  <div className="key-elements">
                    <span className="elements-label">Include:</span>
                    <ul>
                      {idea.structured_data.key_elements.map((element, i) => (
                        <li key={i}>{element}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {idea.structured_data?.best_timing && (
                  <div className="timing">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12,6 12,12 16,14" />
                    </svg>
                    <span>{idea.structured_data.best_timing}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Challenges Overcome */}
      {storyThemes[0]?.structured_data?.challenges_overcome?.length > 0 && (
        <div className="marketing-section">
          <h4>Challenges Overcome</h4>
          <ul className="challenges-list">
            {storyThemes[0].structured_data.challenges_overcome.map((challenge, index) => (
              <li key={index}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                  <polyline points="20,6 9,17 4,12" />
                </svg>
                {challenge}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default MarketingTab;
