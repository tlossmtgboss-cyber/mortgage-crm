import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { leadsAPI, loansAPI, conversationsAPI } from '../services/api';
import AIAssistant from '../components/AIAssistant';
import './ClientProfile.css';

function ClientProfile() {
  const { type, id } = useParams(); // type: 'lead' or 'loan'
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assistantOpen, setAssistantOpen] = useState(false);

  useEffect(() => {
    loadClientData();
    loadConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, id]);

  const loadClientData = async () => {
    try {
      setLoading(true);
      const data = type === 'lead'
        ? await leadsAPI.getById(id)
        : await loansAPI.getById(id);
      setClient(data);
    } catch (error) {
      console.error('Failed to load client:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadConversations = async () => {
    try {
      const params = type === 'lead' ? { lead_id: id } : { loan_id: id };
      const data = await conversationsAPI.getAll(params);
      setConversations(data);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  if (loading) {
    return <div className="loading">Loading client profile...</div>;
  }

  if (!client) {
    return <div className="error">Client not found</div>;
  }

  const context = type === 'lead' ? { lead_id: id } : { loan_id: id };

  return (
    <div className="client-profile-page">
      <div className="profile-header">
        <button className="back-button" onClick={() => navigate(-1)}>
          ← Back
        </button>
        <h1>{type === 'lead' ? client.name : client.borrower_name}</h1>
        <div className="profile-actions">
          <button className="btn-ai" onClick={() => setAssistantOpen(!assistantOpen)}>
            {assistantOpen ? 'Close' : 'Open'} AI Assistant
          </button>
        </div>
      </div>

      <div className={`profile-content ${assistantOpen ? 'with-assistant' : ''}`}>
        <div className="profile-main">
          {/* Client Information */}
          <div className="info-card">
            <h2>Client Information</h2>
            <div className="info-grid">
              {type === 'lead' ? (
                <>
                  <div className="info-item">
                    <label>Email</label>
                    <p>{client.email || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Phone</label>
                    <p>{client.phone || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Stage</label>
                    <p className="badge">{client.stage}</p>
                  </div>
                  <div className="info-item">
                    <label>Source</label>
                    <p>{client.source || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Credit Score</label>
                    <p>{client.credit_score || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>AI Score</label>
                    <p className={`score score-${client.ai_score >= 80 ? 'high' : client.ai_score >= 50 ? 'medium' : 'low'}`}>
                      {client.ai_score}/100
                    </p>
                  </div>
                  <div className="info-item">
                    <label>Preapproval Amount</label>
                    <p>{client.preapproval_amount ? `$${client.preapproval_amount.toLocaleString()}` : 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Next Action</label>
                    <p>{client.next_action || 'N/A'}</p>
                  </div>
                </>
              ) : (
                <>
                  <div className="info-item">
                    <label>Loan Number</label>
                    <p>{client.loan_number}</p>
                  </div>
                  <div className="info-item">
                    <label>Stage</label>
                    <p className="badge">{client.stage}</p>
                  </div>
                  <div className="info-item">
                    <label>Loan Amount</label>
                    <p>${client.amount?.toLocaleString()}</p>
                  </div>
                  <div className="info-item">
                    <label>Program</label>
                    <p>{client.program || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Interest Rate</label>
                    <p>{client.rate ? `${client.rate}%` : 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Property Address</label>
                    <p>{client.property_address || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Closing Date</label>
                    <p>{client.closing_date ? new Date(client.closing_date).toLocaleDateString() : 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>Days in Stage</label>
                    <p>{client.days_in_stage} days</p>
                  </div>
                  <div className="info-item">
                    <label>Processor</label>
                    <p>{client.processor || 'N/A'}</p>
                  </div>
                  <div className="info-item">
                    <label>SLA Status</label>
                    <p className={`badge badge-${client.sla_status}`}>{client.sla_status}</p>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Conversation History */}
          <div className="conversations-card">
            <h2>Conversation History</h2>
            {conversations.length === 0 ? (
              <p className="empty-state">No conversations yet. Use the AI Assistant to start chatting.</p>
            ) : (
              <div className="conversations-list">
                {conversations.map((conv) => (
                  <div key={conv.id} className={`conversation-item ${conv.role}`}>
                    <div className="conv-header">
                      <span className="conv-role">{conv.role === 'user' ? 'You' : 'AI Assistant'}</span>
                      <span className="conv-time">
                        {new Date(conv.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="conv-content">
                      {conv.role === 'user' ? conv.message : conv.response}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* AI Assistant Sidebar */}
        {assistantOpen && (
          <div className="assistant-sidebar">
            <AIAssistant
              isOpen={true}
              onClose={() => setAssistantOpen(false)}
              context={context}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default ClientProfile;
