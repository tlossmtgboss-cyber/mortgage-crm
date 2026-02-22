import React, { useState } from 'react';
import './HelpPanel.css';

/**
 * HelpPanel - Slide-out help documentation panel
 * Provides contextual help articles organized by category
 */
const HelpPanel = ({ isOpen, onClose }) => {
  const [activeCategory, setActiveCategory] = useState('getting-started');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedArticle, setExpandedArticle] = useState(null);

  const helpContent = {
    'getting-started': {
      title: 'Getting Started',
      icon: '🚀',
      articles: [
        {
          id: 'first-call',
          title: 'Your First Call',
          content: `All Telnyx calls through Perennia AI are automatically recorded.

**How it works:**
1. Click "Make Call" in the top navigation
2. Enter borrower's phone number
3. Have your conversation normally
4. After the call ends, go to "Meetings" to view:
   - Full transcript with timestamps
   - AI summary of key points
   - Action items automatically extracted
   - Performance analytics and coaching

**Tip:** The AI starts analyzing as soon as the call ends. Give it 1-2 minutes to process.`
        },
        {
          id: 'recording-clips',
          title: 'Recording Video Clips',
          content: `Video clips let you send personalized screen + camera recordings to borrowers.

**To record a clip:**
1. Go to Clips → New Clip
2. Choose a template (optional)
3. Select recording mode:
   - Screen + Camera (recommended)
   - Screen only
   - Camera only
4. Click Record and grant permissions
5. Record your message (up to 10 minutes)
6. Preview and save

**Sharing:**
- Click "Share" to generate a link
- Set expiration (optional)
- Send link via email/SMS
- Get notified when viewed`
        },
        {
          id: 'understanding-analytics',
          title: 'Understanding Analytics',
          content: `After each call, you get AI-powered performance analytics.

**Key metrics:**
- **Engagement Score:** Overall conversation quality (0-1.0)
- **Talk-Listen Ratio:** Balance between speaking/listening (target: 40-60%)
- **Questions Asked:** Number of discovery questions
- **Sentiment:** Positive vs negative language
- **Filler Words:** Um, uh, like, etc.

**AI Coaching:**
You'll see personalized recommendations to improve, categorized by priority (high/medium/low).`
        }
      ]
    },
    'meetings': {
      title: 'Meeting Recording',
      icon: '📞',
      articles: [
        {
          id: 'how-recording-works',
          title: 'How Recording Works',
          content: `Every Telnyx call is automatically recorded to secure cloud storage (S3).

**Recording process:**
1. Call starts → Recording begins
2. Call ends → File uploaded to S3
3. Audio extracted → Sent to Whisper/Deepgram
4. Transcript generated → AI analysis runs
5. You're notified → View in Meetings tab

**What's analyzed:**
- Full word-level transcript with timestamps
- Meeting summary and key points
- Action items
- Performance metrics
- Borrower concerns detected
- Compliance risks (if any)`
        },
        {
          id: 'viewing-transcripts',
          title: 'Viewing Transcripts',
          content: `Transcripts are synchronized with audio for easy navigation.

**Features:**
- Click any transcript word → Jump to that moment in audio
- Search within transcript
- Download as text or PDF
- Share specific moments by timestamp

**Transcript accuracy:**
We use OpenAI Whisper and Deepgram for industry-leading accuracy (95%+ for clear audio).`
        }
      ]
    },
    'clips': {
      title: 'Video Clips',
      icon: '🎬',
      articles: [
        {
          id: 'recording-best-practices',
          title: 'Recording Best Practices',
          content: `Tips for recording high-quality clips:

**Before recording:**
- Close unnecessary tabs/applications
- Test your microphone
- Choose a quiet location
- Prepare talking points (use templates!)

**During recording:**
- Look at the camera, not the screen
- Speak clearly and at a moderate pace
- Use the borrower's name
- Keep it under 5 minutes if possible

**After recording:**
- Preview before sharing
- Add a title that explains what it's about
- Set expiration for sensitive content`
        },
        {
          id: 'sharing-tracking',
          title: 'Sharing & Tracking',
          content: `Share clips and see exactly who viewed them.

**Sharing options:**
- Generate link (works for anyone with the link)
- Set expiration date (7, 30, 90 days, or custom)
- Require email to view (capture leads)
- Password protect (for sensitive info)
- Allow/disable downloading

**View tracking:**
- See who viewed (name/email if provided)
- How long they watched
- Completion rate (did they watch it all?)
- Get email notification when viewed`
        },
        {
          id: 'templates',
          title: 'Templates',
          content: `Pre-built templates for common mortgage scenarios:

**Rate Lock Explanation**
Walk borrowers through when/why to lock their rate.

**Document Checklist**
Show exactly what docs you need and where to upload.

**Pre-Approval Congratulations**
Celebrate the milestone and explain next steps.

**Closing Timeline**
Visual walkthrough of the closing process.

**Post-Closing Thank You**
Personal thank you and referral request.

Templates include suggested talking points and duration guidance.`
        }
      ]
    },
    'analytics': {
      title: 'Analytics & Coaching',
      icon: '📊',
      articles: [
        {
          id: 'metrics-explained',
          title: 'Performance Metrics Explained',
          content: `Understanding your analytics:

**Engagement Score (0.0-1.0):**
Composite score based on talk-listen ratio, questions asked, interruptions, and speaking pace.
- 0.8-1.0: Excellent
- 0.6-0.8: Good
- 0.4-0.6: Needs improvement
- <0.4: Critical

**Talk-Listen Ratio:**
Percentage of time you spent talking vs listening.
- Target: 40-60% (balanced conversation)
- >70%: You're dominating the conversation
- <30%: You're not engaging enough

**Questions Asked:**
Number of questions you asked during the call.
- Target: 8-15 questions per 30-minute call
- More questions = better discovery`
        },
        {
          id: 'ai-coaching',
          title: 'AI Coaching Recommendations',
          content: `The AI gives you specific recommendations after each call.

**Coaching categories:**
- **Listening:** Talk-listen balance
- **Pacing:** Speaking speed and monologue length
- **Questioning:** Discovery and engagement
- **Clarity:** Filler words and confidence
- **Mortgage Knowledge:** Industry-specific guidance

**Priority levels:**
- **High:** Address immediately (red flags)
- **Medium:** Important for improvement
- **Low:** Nice-to-have polish

**Tracking progress:**
View your improvement over time in the Analytics tab.`
        }
      ]
    },
    'troubleshooting': {
      title: 'Troubleshooting',
      icon: '🔧',
      articles: [
        {
          id: 'recording-issues',
          title: 'Recording Issues',
          content: `**Recording doesn't start:**
- Check microphone permissions in browser settings
- Try a different browser (Chrome recommended)
- Disable browser extensions that block media

**Poor audio quality:**
- Use a headset or external microphone
- Check microphone levels in system settings
- Reduce background noise

**Transcript is inaccurate:**
- Speak clearly and at moderate pace
- Reduce overlapping speech
- Use better audio equipment
- Submit feedback to improve AI`
        },
        {
          id: 'clip-problems',
          title: 'Clip Recording Problems',
          content: `**Can't record screen:**
- Grant screen sharing permission
- Chrome/Edge recommended (best compatibility)
- Restart browser if permission denied

**Video won't upload:**
- Check internet connection
- File size limit is 500MB
- Try a shorter clip
- Clear browser cache

**Processing takes too long:**
- Normal: 1-3 minutes for transcription
- If >10 minutes, refresh page
- Contact support if stuck on "Processing"`
        }
      ]
    }
  };

  // Search functionality
  const searchArticles = () => {
    if (!searchTerm.trim()) return null;

    const results = [];
    Object.entries(helpContent).forEach(([categoryKey, category]) => {
      category.articles.forEach(article => {
        if (
          article.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
          article.content.toLowerCase().includes(searchTerm.toLowerCase())
        ) {
          results.push({
            ...article,
            category: category.title,
            categoryKey
          });
        }
      });
    });

    return results;
  };

  const searchResults = searchTerm ? searchArticles() : null;

  // Render markdown-like content
  const renderContent = (content) => {
    return content.split('\n').map((line, idx) => {
      // Bold text
      if (line.startsWith('**') && line.endsWith('**')) {
        return <h4 key={idx} className="content-heading">{line.slice(2, -2)}</h4>;
      }
      // Bold inline
      const boldRegex = /\*\*([^*]+)\*\*/g;
      if (boldRegex.test(line)) {
        const parts = line.split(boldRegex);
        return (
          <p key={idx}>
            {parts.map((part, i) =>
              i % 2 === 1 ? <strong key={i}>{part}</strong> : part
            )}
          </p>
        );
      }
      // List item
      if (line.startsWith('- ')) {
        return <li key={idx}>{line.slice(2)}</li>;
      }
      // Numbered list
      if (/^\d+\.\s/.test(line)) {
        return <li key={idx} className="numbered">{line.replace(/^\d+\.\s/, '')}</li>;
      }
      // Empty line
      if (!line.trim()) {
        return <br key={idx} />;
      }
      // Regular paragraph
      return <p key={idx}>{line}</p>;
    });
  };

  if (!isOpen) return null;

  return (
    <div className="help-panel-overlay" onClick={onClose}>
      <div className="help-panel" onClick={(e) => e.stopPropagation()}>
        <div className="help-panel-header">
          <h2>Help & Documentation</h2>
          <button className="close-button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="help-search">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            placeholder="Search help articles..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button
              className="clear-search"
              onClick={() => setSearchTerm('')}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>

        <div className="help-panel-content">
          {searchResults ? (
            <div className="search-results">
              <h3>{searchResults.length} results for "{searchTerm}"</h3>
              {searchResults.length === 0 ? (
                <p className="no-results">No articles found. Try different keywords.</p>
              ) : (
                searchResults.map((result) => (
                  <div
                    key={result.id}
                    className="search-result"
                    onClick={() => {
                      setActiveCategory(result.categoryKey);
                      setExpandedArticle(result.id);
                      setSearchTerm('');
                    }}
                  >
                    <strong>{result.title}</strong>
                    <span className="result-category">{result.category}</span>
                  </div>
                ))
              )}
            </div>
          ) : (
            <>
              <div className="help-sidebar">
                {Object.entries(helpContent).map(([key, category]) => (
                  <button
                    key={key}
                    className={`category-button ${activeCategory === key ? 'active' : ''}`}
                    onClick={() => {
                      setActiveCategory(key);
                      setExpandedArticle(null);
                    }}
                  >
                    <span className="category-icon">{category.icon}</span>
                    <span>{category.title}</span>
                  </button>
                ))}
              </div>

              <div className="help-articles">
                <h3>
                  <span className="section-icon">{helpContent[activeCategory].icon}</span>
                  {helpContent[activeCategory].title}
                </h3>
                {helpContent[activeCategory].articles.map((article) => (
                  <details
                    key={article.id}
                    className="help-article"
                    open={expandedArticle === article.id}
                    onClick={(e) => {
                      if (e.target.tagName === 'SUMMARY') {
                        setExpandedArticle(
                          expandedArticle === article.id ? null : article.id
                        );
                      }
                    }}
                  >
                    <summary>{article.title}</summary>
                    <div className="article-content">
                      {renderContent(article.content)}
                    </div>
                  </details>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="help-panel-footer">
          <p>Still need help?</p>
          <div className="footer-links">
            <a href="mailto:support@pipeline360.com" className="footer-link">
              <span>✉️</span> Email Support
            </a>
            <a href="/help/videos" className="footer-link">
              <span>🎥</span> Video Tutorials
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HelpPanel;
