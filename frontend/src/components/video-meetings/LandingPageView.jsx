import React from 'react';
import { getVideoEmbedUrl } from './utils';

const LandingPageView = ({
  landingPageSettings, setLandingPageSettings,
  previewMode, setPreviewMode,
  savingLandingPage, handleSaveLandingPage,
  DEFAULT_LANDING_PAGE
}) => {
  const videoEmbedUrl = getVideoEmbedUrl(landingPageSettings.video_url, landingPageSettings.video_type);

  if (previewMode) {
    return (
      <div className="scheduler-landing-page-view">
        <div className="landing-page-header">
          <div className="header-content">
            <h3>Landing Page Preview</h3>
            <p className="description">This is how your video meeting booking page will appear to clients.</p>
          </div>
          <div className="preview-toggle">
            <span>Preview Mode</span>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={previewMode}
                onChange={(e) => setPreviewMode(e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div className="landing-page-preview">
          <div className={`preview-container bg-${landingPageSettings.background_style}`}>
            <div className="preview-header">
              {landingPageSettings.show_company_logo && landingPageSettings.logo_url && (
                <img src={landingPageSettings.logo_url} alt="Logo" className="preview-logo" />
              )}
              <h2 style={{ color: landingPageSettings.accent_color }}>
                {landingPageSettings.headline || 'Schedule a Video Meeting'}
              </h2>
              <p className="preview-subheadline">{landingPageSettings.subheadline}</p>
            </div>

            {videoEmbedUrl && (
              <div className="preview-video">
                <iframe
                  src={videoEmbedUrl}
                  title="Introduction Video"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            )}

            {landingPageSettings.show_profile && (landingPageSettings.profile_name || landingPageSettings.profile_picture_url) && (
              <div className="preview-profile">
                {landingPageSettings.profile_picture_url && (
                  <img src={landingPageSettings.profile_picture_url} alt="Profile" className="preview-profile-picture" />
                )}
                <div className="preview-profile-info">
                  {landingPageSettings.profile_name && <h4>{landingPageSettings.profile_name}</h4>}
                  {landingPageSettings.profile_title && <p className="profile-title">{landingPageSettings.profile_title}</p>}
                  {landingPageSettings.profile_bio && <p className="profile-bio">{landingPageSettings.profile_bio}</p>}
                </div>
              </div>
            )}

            {landingPageSettings.description && (
              <div className="preview-description">
                <h4>About This Meeting</h4>
                <p>{landingPageSettings.description}</p>
              </div>
            )}

            <div className="calendar-mock">
              <p>Calendar widget will appear here</p>
            </div>

            {landingPageSettings.show_social_proof && landingPageSettings.testimonial_text && (
              <div className="preview-testimonial">
                <blockquote>"{landingPageSettings.testimonial_text}"</blockquote>
                {landingPageSettings.testimonial_author && (
                  <cite>-- {landingPageSettings.testimonial_author}</cite>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Edit Mode
  return (
    <div className="scheduler-landing-page-view">
      <div className="landing-page-header">
        <div className="header-content">
          <h3>Landing Page Customization</h3>
          <p className="description">Customize how your video meeting booking page looks to clients.</p>
        </div>
        <div className="preview-toggle">
          <span>Preview Mode</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={previewMode}
              onChange={(e) => setPreviewMode(e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div className="landing-page-editor">
        {/* Branding Section */}
        <div className="editor-section">
          <h4><span className="section-icon">&#x1F3A8;</span> Branding</h4>
          <div className="form-group">
            <label>Company Logo URL</label>
            <input
              type="text"
              value={landingPageSettings.logo_url}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, logo_url: e.target.value})}
              placeholder="https://example.com/logo.png"
            />
            <span className="help-text">Enter the URL of your company logo image</span>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Accent Color</label>
              <div className="color-input-group">
                <input
                  type="color"
                  value={landingPageSettings.accent_color}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, accent_color: e.target.value})}
                />
                <input
                  type="text"
                  value={landingPageSettings.accent_color}
                  onChange={(e) => setLandingPageSettings({...landingPageSettings, accent_color: e.target.value})}
                />
              </div>
            </div>
            <div className="form-group">
              <label>Background Style</label>
              <select
                value={landingPageSettings.background_style}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, background_style: e.target.value})}
              >
                <option value="white">White</option>
                <option value="light">Light Gray</option>
                <option value="gradient">Gradient</option>
              </select>
            </div>
          </div>
        </div>

        {/* Video Section */}
        <div className="editor-section">
          <h4><span className="section-icon">&#x1F3A5;</span> Introduction Video</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Video Platform</label>
              <select
                value={landingPageSettings.video_type}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, video_type: e.target.value})}
              >
                <option value="youtube">YouTube</option>
                <option value="vimeo">Vimeo</option>
                <option value="loom">Loom</option>
                <option value="custom">Custom Embed</option>
              </select>
            </div>
            <div className="form-group">
              <label>Video URL</label>
              <input
                type="text"
                value={landingPageSettings.video_url}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, video_url: e.target.value})}
                placeholder="https://youtube.com/watch?v=..."
              />
            </div>
          </div>
          {videoEmbedUrl && (
            <div className="video-preview">
              <iframe
                src={videoEmbedUrl}
                title="Video Preview"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          )}
        </div>

        {/* Profile Section */}
        <div className="editor-section">
          <h4><span className="section-icon">&#x1F464;</span> Your Profile</h4>
          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={landingPageSettings.show_profile}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, show_profile: e.target.checked})}
              />
              Show profile section on landing page
            </label>
          </div>
          <div className="form-group">
            <label>Profile Picture URL</label>
            <input
              type="text"
              value={landingPageSettings.profile_picture_url}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_picture_url: e.target.value})}
              placeholder="https://example.com/photo.jpg"
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Your Name</label>
              <input
                type="text"
                value={landingPageSettings.profile_name}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_name: e.target.value})}
                placeholder="John Smith"
              />
            </div>
            <div className="form-group">
              <label>Title/Role</label>
              <input
                type="text"
                value={landingPageSettings.profile_title}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_title: e.target.value})}
                placeholder="Senior Loan Officer"
              />
            </div>
          </div>
          <div className="form-group">
            <label>Short Bio</label>
            <textarea
              value={landingPageSettings.profile_bio}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, profile_bio: e.target.value})}
              placeholder="Brief introduction about yourself..."
              rows={2}
            />
          </div>
        </div>

        {/* Content Section */}
        <div className="editor-section">
          <h4><span className="section-icon">&#x1F4DD;</span> Page Content</h4>
          <div className="form-group">
            <label>Headline</label>
            <input
              type="text"
              value={landingPageSettings.headline}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, headline: e.target.value})}
              placeholder="Schedule a Video Meeting"
            />
          </div>
          <div className="form-group">
            <label>Subheadline</label>
            <input
              type="text"
              value={landingPageSettings.subheadline}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, subheadline: e.target.value})}
              placeholder="Choose a time that works for you"
            />
          </div>
          <div className="form-group">
            <label>Meeting Description/Agenda</label>
            <textarea
              value={landingPageSettings.description}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, description: e.target.value})}
              placeholder="Describe what the meeting will cover..."
              rows={4}
            />
            <span className="help-text">Help clients understand what to expect from the video meeting</span>
          </div>
        </div>

        {/* Social Proof Section */}
        <div className="editor-section">
          <h4><span className="section-icon">&#x2B50;</span> Social Proof</h4>
          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={landingPageSettings.show_social_proof}
                onChange={(e) => setLandingPageSettings({...landingPageSettings, show_social_proof: e.target.checked})}
              />
              Show testimonial on landing page
            </label>
          </div>
          <div className="form-group">
            <label>Testimonial Text</label>
            <textarea
              value={landingPageSettings.testimonial_text}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, testimonial_text: e.target.value})}
              placeholder="What a satisfied client said about working with you..."
              rows={3}
            />
          </div>
          <div className="form-group">
            <label>Testimonial Author</label>
            <input
              type="text"
              value={landingPageSettings.testimonial_author}
              onChange={(e) => setLandingPageSettings({...landingPageSettings, testimonial_author: e.target.value})}
              placeholder="Jane D., First-time Homebuyer"
            />
          </div>
        </div>
      </div>

      <div className="landing-page-actions">
        <button
          className="reset-landing-btn"
          onClick={() => setLandingPageSettings({ ...DEFAULT_LANDING_PAGE })}
        >
          Reset to Defaults
        </button>
        <button
          className="save-landing-btn"
          onClick={handleSaveLandingPage}
          disabled={savingLandingPage}
        >
          {savingLandingPage ? 'Saving...' : 'Save Landing Page'}
        </button>
      </div>
    </div>
  );
};

export default LandingPageView;
