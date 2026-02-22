/**
 * Conversation Intelligence Recording Detail Page
 *
 * Detailed view for a specific call recording:
 * - Audio player
 * - Transcription with speaker labels
 * - AI analysis results
 * - QA scorecards
 * - Coaching clip creation
 */

import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
import { toast } from '../utils/toast';
  useRecordingDetail,
  useTranscriptionPolling,
  useQARubrics,
} from '../hooks/useConversationIntelligence';
import { coachingApi } from '../services/conversationIntelligenceApi';
import './ConversationIntelligenceRecordingDetail.css';

function ConversationIntelligenceRecordingDetail() {
  const { recordingId } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef(null);

  const [activeTab, setActiveTab] = useState('transcript');
  const [selectedSegmentIndex, setSelectedSegmentIndex] = useState(null);
  const [isCreatingClip, setIsCreatingClip] = useState(false);
  const [clipForm, setClipForm] = useState({
    title: '',
    description: '',
    category: 'general',
    startTime: 0,
    endTime: 0,
  });

  const {
    recording,
    transcription,
    analysis,
    scorecards,
    loading,
    error,
    refetch,
    startTranscription,
    startAnalysis,
    createScorecard,
  } = useRecordingDetail(recordingId);

  const { rubrics } = useQARubrics();

  const {
    transcription: pollingTranscription,
    isPolling,
    startPolling,
  } = useTranscriptionPolling(recordingId, false);

  // Update transcription from polling
  useEffect(() => {
    if (pollingTranscription?.status === 'completed') {
      refetch();
    }
  }, [pollingTranscription, refetch]);

  // Format helpers
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (seconds) => {
    if (!seconds && seconds !== 0) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getGradeColor = (grade) => {
    const colors = {
      A: '#22c55e',
      B: '#84cc16',
      C: '#eab308',
      D: '#f97316',
      F: '#ef4444',
    };
    return colors[grade] || '#6b7280';
  };

  const getSpeakerColor = (speaker) => {
    const colors = {
      agent: '#6366f1',
      customer: '#10b981',
      unknown: '#64748b',
    };
    return colors[speaker?.toLowerCase()] || colors.unknown;
  };

  // Audio player controls
  const seekToTime = (seconds) => {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds;
      audioRef.current.play();
    }
  };

  // Handle transcription start
  const handleStartTranscription = async () => {
    const success = await startTranscription({
      audioUrl: recording.audioUrl,
      provider: 'deepgram',
    });
    if (success) {
      startPolling();
    }
  };

  // Handle analysis start
  const handleStartAnalysis = async () => {
    await startAnalysis({
      extractTopics: true,
      extractActionItems: true,
      extractObjections: true,
      extractQuestions: true,
      checkCompliance: true,
    });
    refetch();
  };

  // Handle QA scoring
  const handleCreateScorecard = async (rubricId) => {
    await createScorecard({
      rubricId,
      useLlmScoring: true,
    });
  };

  // Handle clip creation
  const handleCreateClip = async () => {
    if (!clipForm.title || clipForm.endTime <= clipForm.startTime) {
      toast.error('Please provide a title and valid time range');
      return;
    }

    try {
      await coachingApi.createClip({
        recordingId,
        title: clipForm.title,
        description: clipForm.description,
        category: clipForm.category,
        startTime: clipForm.startTime,
        endTime: clipForm.endTime,
      });
      setIsCreatingClip(false);
      setClipForm({ title: '', description: '', category: 'general', startTime: 0, endTime: 0 });
      toast.success('Coaching clip created successfully!');
    } catch (err) {
      toast.error('Failed to create clip: ' + err.message);
    }
  };

  // Render transcript tab
  const renderTranscript = () => {
    if (!transcription) {
      return (
        <div className="cird-empty-state">
          <i className="fas fa-microphone-slash"></i>
          <h3>No Transcription Yet</h3>
          <p>Transcribe this recording to view the conversation text.</p>
          {recording?.audioUrl && (
            <button
              className="cird-btn cird-btn-primary"
              onClick={handleStartTranscription}
              disabled={isPolling}
            >
              {isPolling ? (
                <>
                  <i className="fas fa-spinner fa-spin"></i> Transcribing...
                </>
              ) : (
                <>
                  <i className="fas fa-play"></i> Start Transcription
                </>
              )}
            </button>
          )}
        </div>
      );
    }

    if (transcription.status === 'processing') {
      return (
        <div className="cird-processing-state">
          <i className="fas fa-spinner fa-spin"></i>
          <h3>Transcribing...</h3>
          <p>This may take a few minutes depending on the call length.</p>
        </div>
      );
    }

    if (transcription.status === 'failed') {
      return (
        <div className="cird-error-state">
          <i className="fas fa-exclamation-circle"></i>
          <h3>Transcription Failed</h3>
          <p>{transcription.errorMessage || 'An error occurred during transcription.'}</p>
          <button className="cird-btn cird-btn-primary" onClick={handleStartTranscription}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      );
    }

    return (
      <div className="cird-transcript">
        <div className="cird-transcript-header">
          <span className="cird-transcript-meta">
            {transcription.wordCount} words | Provider: {transcription.provider}
          </span>
          <div className="cird-transcript-actions">
            <button
              className="cird-btn cird-btn-sm"
              onClick={() => {
                navigator.clipboard.writeText(transcription.transcriptText);
                toast.success('Transcript copied to clipboard!');
              }}
            >
              <i className="fas fa-copy"></i> Copy
            </button>
          </div>
        </div>

        <div className="cird-transcript-segments">
          {transcription.segments?.map((segment, index) => (
            <div
              key={index}
              className={`cird-segment ${selectedSegmentIndex === index ? 'selected' : ''}`}
              onClick={() => {
                setSelectedSegmentIndex(index);
                seekToTime(segment.startTime);
              }}
            >
              <div className="cird-segment-header">
                <span
                  className="cird-segment-speaker"
                  style={{ backgroundColor: getSpeakerColor(segment.speaker) }}
                >
                  {segment.speaker || 'Speaker'}
                </span>
                <span className="cird-segment-time">
                  {formatTimestamp(segment.startTime)}
                </span>
              </div>
              <p className="cird-segment-text">{segment.text}</p>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Render analysis tab
  const renderAnalysis = () => {
    if (!analysis) {
      return (
        <div className="cird-empty-state">
          <i className="fas fa-brain"></i>
          <h3>No Analysis Yet</h3>
          <p>Run AI analysis to get insights from this call.</p>
          {transcription?.status === 'completed' && (
            <button className="cird-btn cird-btn-primary" onClick={handleStartAnalysis}>
              <i className="fas fa-play"></i> Run Analysis
            </button>
          )}
          {!transcription && (
            <p className="cird-hint">Transcription is required before analysis.</p>
          )}
        </div>
      );
    }

    if (analysis.status === 'processing') {
      return (
        <div className="cird-processing-state">
          <i className="fas fa-spinner fa-spin"></i>
          <h3>Analyzing...</h3>
          <p>AI is extracting insights from the conversation.</p>
        </div>
      );
    }

    return (
      <div className="cird-analysis">
        {/* Summary */}
        <div className="cird-analysis-section">
          <h4><i className="fas fa-align-left"></i> Summary</h4>
          <p>{analysis.summary || 'No summary available.'}</p>
        </div>

        {/* Key Topics */}
        {analysis.keyTopics?.length > 0 && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-tags"></i> Key Topics</h4>
            <div className="cird-topics">
              {analysis.keyTopics.map((topic, index) => (
                <span key={index} className="cird-topic-tag">{topic}</span>
              ))}
            </div>
          </div>
        )}

        {/* Sentiment */}
        {analysis.sentiment && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-smile"></i> Sentiment</h4>
            <div className="cird-sentiment">
              <div className={`cird-sentiment-badge ${analysis.sentiment.overall}`}>
                {analysis.sentiment.overall}
              </div>
              <span className="cird-sentiment-trajectory">
                Trajectory: {analysis.sentiment.trajectory}
              </span>
            </div>
          </div>
        )}

        {/* Talk Ratio */}
        {analysis.talkRatio && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-chart-pie"></i> Talk Ratio</h4>
            <div className="cird-talk-ratio">
              <div className="cird-talk-ratio-bar">
                <div
                  className="cird-talk-ratio-agent"
                  style={{ width: `${analysis.talkRatio.agentPercentage}%` }}
                >
                  Agent: {analysis.talkRatio.agentPercentage?.toFixed(0)}%
                </div>
                <div
                  className="cird-talk-ratio-customer"
                  style={{ width: `${analysis.talkRatio.customerPercentage}%` }}
                >
                  Customer: {analysis.talkRatio.customerPercentage?.toFixed(0)}%
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Action Items */}
        {analysis.actionItems?.length > 0 && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-tasks"></i> Action Items</h4>
            <ul className="cird-action-items">
              {analysis.actionItems.map((item, index) => (
                <li key={index}>
                  <i className="fas fa-circle"></i>
                  {item.description}
                  {item.priority && (
                    <span className={`cird-priority ${item.priority}`}>{item.priority}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Objections */}
        {analysis.objections?.length > 0 && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-hand-paper"></i> Objections Detected</h4>
            <div className="cird-objections">
              {analysis.objections.map((objection, index) => (
                <div key={index} className="cird-objection-item">
                  <span className="cird-objection-type">{objection.type}</span>
                  <p>{objection.text}</p>
                  {objection.handled && (
                    <span className={`cird-handling-quality ${objection.handlingQuality}`}>
                      {objection.handlingQuality}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Questions */}
        {analysis.questions?.length > 0 && (
          <div className="cird-analysis-section">
            <h4><i className="fas fa-question-circle"></i> Questions Raised</h4>
            <div className="cird-questions">
              {analysis.questions.map((question, index) => (
                <div key={index} className="cird-question-item">
                  <span className="cird-question-by">{question.askedBy}</span>
                  <p>{question.text}</p>
                  {question.answered && question.answer && (
                    <div className="cird-question-answer">
                      <strong>Answer:</strong> {question.answer}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Render QA tab
  const renderQA = () => {
    if (scorecards.length === 0) {
      return (
        <div className="cird-empty-state">
          <i className="fas fa-star-half-alt"></i>
          <h3>No QA Scorecards Yet</h3>
          <p>Create a QA scorecard to evaluate this call.</p>
          {transcription?.status === 'completed' && (
            <div className="cird-qa-rubric-select">
              <p>Select a rubric to score this call:</p>
              <div className="cird-rubric-buttons">
                {rubrics.map((rubric) => (
                  <button
                    key={rubric.id}
                    className="cird-btn cird-btn-secondary"
                    onClick={() => handleCreateScorecard(rubric.id)}
                  >
                    {rubric.name}
                    {rubric.isDefault && <span className="cird-default-badge">Default</span>}
                  </button>
                ))}
                <button
                  className="cird-btn cird-btn-primary"
                  onClick={() => handleCreateScorecard(null)}
                >
                  Use Default Rubric
                </button>
              </div>
            </div>
          )}
          {!transcription && (
            <p className="cird-hint">Transcription is required before QA scoring.</p>
          )}
        </div>
      );
    }

    const latestScorecard = scorecards[0];

    return (
      <div className="cird-qa">
        {/* Score Summary */}
        <div className="cird-qa-summary">
          <div
            className="cird-qa-grade"
            style={{ backgroundColor: getGradeColor(latestScorecard.grade) }}
          >
            {latestScorecard.grade}
          </div>
          <div className="cird-qa-score-info">
            <span className="cird-qa-score-value">
              {latestScorecard.percentageScore?.toFixed(0)}%
            </span>
            <span className="cird-qa-score-detail">
              {latestScorecard.totalScore} / {latestScorecard.maxPossibleScore} points
            </span>
            <span className="cird-qa-rubric">
              Rubric: {latestScorecard.rubricName}
            </span>
          </div>
        </div>

        {/* Scorecard Items */}
        <div className="cird-qa-items">
          <h4>Scoring Breakdown</h4>
          {latestScorecard.items?.map((item, index) => (
            <div key={index} className="cird-qa-item">
              <div className="cird-qa-item-header">
                <span className="cird-qa-item-name">{item.criterionName}</span>
                <span className="cird-qa-item-category">{item.category}</span>
              </div>
              <div className="cird-qa-item-score">
                <div className="cird-qa-item-bar-container">
                  <div
                    className="cird-qa-item-bar"
                    style={{ width: `${(item.score / item.maxScore) * 100}%` }}
                  ></div>
                </div>
                <span className="cird-qa-item-value">
                  {item.score} / {item.maxScore}
                </span>
              </div>
              {item.notes && (
                <p className="cird-qa-item-notes">{item.notes}</p>
              )}
            </div>
          ))}
        </div>

        {/* Recommendations */}
        {latestScorecard.recommendations?.length > 0 && (
          <div className="cird-qa-recommendations">
            <h4><i className="fas fa-lightbulb"></i> Recommendations</h4>
            <ul>
              {latestScorecard.recommendations.map((rec, index) => (
                <li key={index}>{rec}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Strengths & Improvements */}
        <div className="cird-qa-feedback-grid">
          {latestScorecard.strengths?.length > 0 && (
            <div className="cird-qa-strengths">
              <h4><i className="fas fa-check-circle"></i> Strengths</h4>
              <ul>
                {latestScorecard.strengths.map((strength, index) => (
                  <li key={index}>{strength}</li>
                ))}
              </ul>
            </div>
          )}
          {latestScorecard.improvements?.length > 0 && (
            <div className="cird-qa-improvements">
              <h4><i className="fas fa-arrow-up"></i> Areas for Improvement</h4>
              <ul>
                {latestScorecard.improvements.map((improvement, index) => (
                  <li key={index}>{improvement}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="cird-loading">
        <i className="fas fa-spinner fa-spin"></i>
        <span>Loading recording...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="cird-error">
        <i className="fas fa-exclamation-circle"></i>
        <h3>Error Loading Recording</h3>
        <p>{error}</p>
        <button className="cird-btn cird-btn-primary" onClick={() => navigate(-1)}>
          <i className="fas fa-arrow-left"></i> Go Back
        </button>
      </div>
    );
  }

  if (!recording) {
    return (
      <div className="cird-not-found">
        <i className="fas fa-search"></i>
        <h3>Recording Not Found</h3>
        <button className="cird-btn cird-btn-primary" onClick={() => navigate('/conversation-intelligence')}>
          <i className="fas fa-arrow-left"></i> Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="cird-page">
      {/* Header */}
      <div className="cird-header">
        <button className="cird-back-btn" onClick={() => navigate('/conversation-intelligence')}>
          <i className="fas fa-arrow-left"></i>
        </button>
        <div className="cird-header-info">
          <h1>Call Recording</h1>
          <span className="cird-header-meta">
            {formatDate(recording.createdAt)} | {recording.agentName || `Agent #${recording.agentId}`}
          </span>
        </div>
        <div className="cird-header-actions">
          <button
            className="cird-btn cird-btn-secondary"
            onClick={() => setIsCreatingClip(true)}
            disabled={!transcription}
          >
            <i className="fas fa-cut"></i> Create Clip
          </button>
        </div>
      </div>

      {/* Recording Info Card */}
      <div className="cird-info-card">
        <div className="cird-info-grid">
          <div className="cird-info-item">
            <span className="cird-info-label">Direction</span>
            <span className="cird-info-value">
              <i className={recording.direction === 'inbound' ? 'fas fa-phone-alt' : 'fas fa-phone-volume'}></i>
              {recording.direction}
            </span>
          </div>
          <div className="cird-info-item">
            <span className="cird-info-label">Duration</span>
            <span className="cird-info-value">{formatDuration(recording.durationSeconds)}</span>
          </div>
          <div className="cird-info-item">
            <span className="cird-info-label">Status</span>
            <span className={`cird-status-badge ${recording.status}`}>{recording.status}</span>
          </div>
          {scorecards.length > 0 && (
            <div className="cird-info-item">
              <span className="cird-info-label">QA Score</span>
              <span
                className="cird-info-value cird-qa-badge"
                style={{ backgroundColor: getGradeColor(scorecards[0].grade) }}
              >
                {scorecards[0].grade} ({scorecards[0].percentageScore?.toFixed(0)}%)
              </span>
            </div>
          )}
        </div>

        {/* Audio Player */}
        {recording.audioUrl && (
          <div className="cird-audio-player">
            <audio ref={audioRef} controls src={recording.audioUrl}>
              Your browser does not support the audio element.
            </audio>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="cird-tabs">
        {[
          { id: 'transcript', label: 'Transcript', icon: 'fas fa-file-alt' },
          { id: 'analysis', label: 'Analysis', icon: 'fas fa-brain' },
          { id: 'qa', label: 'QA Score', icon: 'fas fa-star' },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`cird-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <i className={tab.icon}></i>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="cird-content">
        {activeTab === 'transcript' && renderTranscript()}
        {activeTab === 'analysis' && renderAnalysis()}
        {activeTab === 'qa' && renderQA()}
      </div>

      {/* Create Clip Modal */}
      {isCreatingClip && (
        <div className="cird-modal-overlay" onClick={() => setIsCreatingClip(false)}>
          <div className="cird-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cird-modal-header">
              <h3>Create Coaching Clip</h3>
              <button className="cird-modal-close" onClick={() => setIsCreatingClip(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="cird-modal-body">
              <label>
                Title *
                <input
                  type="text"
                  value={clipForm.title}
                  onChange={(e) => setClipForm({ ...clipForm, title: e.target.value })}
                  placeholder="e.g., Great objection handling"
                />
              </label>
              <label>
                Description
                <textarea
                  value={clipForm.description}
                  onChange={(e) => setClipForm({ ...clipForm, description: e.target.value })}
                  placeholder="Optional description..."
                />
              </label>
              <label>
                Category
                <select
                  value={clipForm.category}
                  onChange={(e) => setClipForm({ ...clipForm, category: e.target.value })}
                >
                  <option value="general">General</option>
                  <option value="best_practice">Best Practice</option>
                  <option value="improvement">Improvement</option>
                  <option value="compliance">Compliance</option>
                  <option value="objection_handling">Objection Handling</option>
                  <option value="closing">Closing</option>
                </select>
              </label>
              <div className="cird-time-range">
                <label>
                  Start Time (seconds)
                  <input
                    type="number"
                    value={clipForm.startTime}
                    onChange={(e) => setClipForm({ ...clipForm, startTime: parseFloat(e.target.value) })}
                    min={0}
                    max={recording.durationSeconds}
                  />
                </label>
                <label>
                  End Time (seconds)
                  <input
                    type="number"
                    value={clipForm.endTime}
                    onChange={(e) => setClipForm({ ...clipForm, endTime: parseFloat(e.target.value) })}
                    min={0}
                    max={recording.durationSeconds}
                  />
                </label>
              </div>
            </div>
            <div className="cird-modal-footer">
              <button className="cird-btn cird-btn-secondary" onClick={() => setIsCreatingClip(false)}>
                Cancel
              </button>
              <button className="cird-btn cird-btn-primary" onClick={handleCreateClip}>
                Create Clip
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ConversationIntelligenceRecordingDetail;
