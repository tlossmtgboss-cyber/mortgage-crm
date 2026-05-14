import React, { useState, useEffect } from 'react';
import { toast } from '../../utils/toast';
import { API_BASE_URL } from './shared/constants';
import { getToken } from '../../utils/tokenStore';

const ApiKeysSection = () => {
  const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);

  useEffect(() => {
    fetchApiKeys();
  }, []);

  const fetchApiKeys = async () => {
    setLoadingApiKeys(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const data = await response.json();
      setApiKeys(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error fetching API keys:', error);
      setApiKeys([]);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const createApiKey = async () => {
    if (!newApiKeyName.trim()) { toast.error('Please enter a name for the API key'); return; }
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newApiKeyName })
      });
      if (response.ok) {
        const data = await response.json();
        setCreatedKey(data.key);
        setNewApiKeyName('');
        fetchApiKeys();
        toast.success('API key created successfully! Make sure to copy it now.');
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        toast.error(`Failed to create API key: ${errorData.detail || errorData.message || 'Unknown error'}`);
      }
    } catch (error) {
      toast.error(`Error creating API key: ${error.message}`);
    }
  };

  const revokeApiKey = async (keyId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      if (response.ok) { toast.success('API key revoked successfully'); fetchApiKeys(); }
      else { toast.error('Failed to revoke API key'); }
    } catch (error) { toast.error('Error revoking API key'); }
  };

  return (
    <div className="api-keys-section">
      <h2>API Keys</h2>
      <p className="section-description">Generate and manage API keys for integrations like Zapier</p>

      <div className="api-key-create-card">
        <h3>Create New API Key</h3>
        <div className="form-group">
          <input type="text" placeholder="Enter API key name (e.g., 'Zapier Integration')" value={newApiKeyName}
            onChange={(e) => setNewApiKeyName(e.target.value)} className="input-field" />
          <button onClick={createApiKey} className="btn-create-key" disabled={!newApiKeyName.trim()}>Generate API Key</button>
        </div>

        {createdKey && (
          <div className="key-created-alert">
            <h4>API Key Created Successfully!</h4>
            <p>Copy this key now - you won't be able to see it again:</p>
            <div className="key-display">
              <code>{createdKey}</code>
              <button onClick={() => { navigator.clipboard.writeText(createdKey); toast.success('API key copied to clipboard!'); }} className="btn-copy">Copy</button>
            </div>
            <button onClick={() => setCreatedKey(null)} className="btn-dismiss">I've saved it</button>
          </div>
        )}
      </div>

      <div className="api-keys-list-card">
        <h3>Your API Keys</h3>
        {loadingApiKeys ? (
          <p>Loading API keys...</p>
        ) : apiKeys.length === 0 ? (
          <div className="empty-state"><p>No API keys yet.</p><p className="empty-hint">Create your first API key above to get started with integrations.</p></div>
        ) : (
          <div className="api-keys-table">
            <table>
              <thead>
                <tr><th>Name</th><th>Key</th><th>Created</th><th>Last Used</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {apiKeys.map((key) => (
                  <tr key={key.id}>
                    <td><strong>{key.name}</strong></td>
                    <td><code>sk_&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;</code></td>
                    <td>{new Date(key.created_at).toLocaleDateString()}</td>
                    <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                    <td><span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>{key.is_active ? 'Active' : 'Revoked'}</span></td>
                    <td>{key.is_active && (<button onClick={() => revokeApiKey(key.id)} className="btn-revoke">Revoke</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="help-card">
        <h4>How to use API Keys</h4>
        <ol>
          <li>Generate an API key by entering a name and clicking "Generate API Key"</li>
          <li>Copy the API key immediately - it will only be shown once</li>
          <li>Use the API key in your integrations by adding it to the Authorization header:<br/><code>Authorization: Bearer sk_your_api_key_here</code></li>
          <li>The API key will work exactly like your login token for all API requests</li>
          <li>Revoke an API key anytime if you suspect it's been compromised</li>
        </ol>
      </div>
    </div>
  );
};

export default ApiKeysSection;
