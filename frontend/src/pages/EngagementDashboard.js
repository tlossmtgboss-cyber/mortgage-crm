import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { toast } from '../utils/toast';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, AreaChart, Area,
} from 'recharts';
import './EngagementDashboard.css';

const COLORS = ['#4f46e5', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

function EngagementDashboard() {
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);
  const [summary, setSummary] = useState(null);
  const [channelData, setChannelData] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [heatmap, setHeatmap] = useState({});
  const [funnel, setFunnel] = useState(null);
  const [dispositions, setDispositions] = useState(null);
  const [activityFeed, setActivityFeed] = useState([]);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [summaryRes, channelRes, leaderRes, heatRes, funnelRes, dispRes, feedRes] =
        await Promise.allSettled([
          api.get(`/api/v1/engagement-dashboard/summary?days=${period}`),
          api.get(`/api/v1/engagement-dashboard/channel-comparison?days=${period}`),
          api.get(`/api/v1/engagement-dashboard/lo-leaderboard?days=${period}`),
          api.get(`/api/v1/engagement-dashboard/hourly-heatmap?days=${period}`),
          api.get(`/api/v1/engagement-dashboard/conversion-funnel?days=${period}`),
          api.get(`/api/v1/dispositions/summary?days=${period}`),
          api.get(`/api/v1/engagement-dashboard/activity-feed?limit=20`),
        ]);

      if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value.data);
      if (channelRes.status === 'fulfilled') setChannelData(channelRes.value.data.channels || []);
      if (leaderRes.status === 'fulfilled') setLeaderboard(leaderRes.value.data.leaderboard || []);
      if (heatRes.status === 'fulfilled') setHeatmap(heatRes.value.data.heatmap || {});
      if (funnelRes.status === 'fulfilled') setFunnel(funnelRes.value.data);
      if (dispRes.status === 'fulfilled') setDispositions(dispRes.value.data);
      if (feedRes.status === 'fulfilled') setActivityFeed(feedRes.value.data.activities || []);
    } catch (err) {
      toast.error('Failed to load engagement dashboard');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="engagement-dashboard">
        <div className="ed-loading">Loading engagement data...</div>
      </div>
    );
  }

  const channelChartData = channelData.map(c => ({
    name: c.channel || 'Unknown',
    total: c.total,
    leads: c.unique_leads,
  }));

  const funnelChartData = funnel ? [
    { name: 'Leads', value: funnel.funnel?.total_leads || 0 },
    { name: 'Contacted', value: funnel.funnel?.contacted || 0 },
    { name: 'Qualified', value: funnel.funnel?.qualified || 0 },
    { name: 'Converted', value: funnel.funnel?.converted || 0 },
  ] : [];

  const dispChartData = dispositions?.dispositions?.map(d => ({
    name: d.disposition,
    count: d.count,
    pct: d.percentage,
  })) || [];

  return (
    <div className="engagement-dashboard">
      <div className="ed-header">
        <h1>Engagement Dashboard</h1>
        <div className="ed-controls">
          <select value={period} onChange={e => setPeriod(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button onClick={fetchData} className="ed-refresh-btn">Refresh</button>
        </div>
      </div>

      {/* KPI Cards */}
      {summary && (
        <div className="ed-kpi-row">
          <div className="ed-kpi-card">
            <div className="ed-kpi-value">{summary.total_activities?.toLocaleString() || 0}</div>
            <div className="ed-kpi-label">Total Activities</div>
          </div>
          <div className="ed-kpi-card">
            <div className="ed-kpi-value">{summary.by_channel?.calls || 0}</div>
            <div className="ed-kpi-label">Calls</div>
          </div>
          <div className="ed-kpi-card">
            <div className="ed-kpi-value">{summary.by_channel?.texts || 0}</div>
            <div className="ed-kpi-label">Texts</div>
          </div>
          <div className="ed-kpi-card">
            <div className="ed-kpi-value">{summary.by_channel?.emails || 0}</div>
            <div className="ed-kpi-label">Emails</div>
          </div>
          <div className="ed-kpi-card">
            <div className="ed-kpi-value">{summary.by_channel?.meetings || 0}</div>
            <div className="ed-kpi-label">Meetings</div>
          </div>
          <div className="ed-kpi-card ed-kpi-highlight">
            <div className="ed-kpi-value">{summary.unique_leads_contacted || 0}</div>
            <div className="ed-kpi-label">Unique Leads</div>
          </div>
        </div>
      )}

      {/* Charts Row */}
      <div className="ed-charts-row">
        {/* Channel Comparison */}
        <div className="ed-chart-card">
          <h3>Activity by Channel</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={channelChartData}>
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="total" fill="#4f46e5" name="Total" />
              <Bar dataKey="leads" fill="#06b6d4" name="Unique Leads" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Conversion Funnel */}
        <div className="ed-chart-card">
          <h3>Conversion Funnel</h3>
          {funnel && (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={funnelChartData} layout="vertical">
                  <XAxis type="number" />
                  <YAxis dataKey="name" type="category" width={80} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
              <div className="ed-funnel-rates">
                <span>Contact: {funnel.rates?.contact_rate || 0}%</span>
                <span>Qualify: {funnel.rates?.qualification_rate || 0}%</span>
                <span>Convert: {funnel.rates?.conversion_rate || 0}%</span>
                <span className="ed-rate-highlight">Overall: {funnel.rates?.overall || 0}%</span>
              </div>
            </>
          )}
        </div>

        {/* Disposition Breakdown */}
        <div className="ed-chart-card">
          <h3>Call Dispositions</h3>
          {dispChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={dispChartData} dataKey="count" nameKey="name" cx="50%" cy="50%"
                  outerRadius={80} label={({ name, pct }) => `${name} ${pct}%`}>
                  {dispChartData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="ed-no-data">No disposition data yet</div>
          )}
        </div>
      </div>

      {/* Second Row */}
      <div className="ed-bottom-row">
        {/* LO Leaderboard */}
        <div className="ed-table-card">
          <h3>LO Leaderboard</h3>
          <table className="ed-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Loan Officer</th>
                <th>Activities</th>
                <th>Calls</th>
                <th>Emails</th>
                <th>Texts</th>
                <th>Leads</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.slice(0, 10).map((lo, i) => (
                <tr key={lo.lo_id}>
                  <td className="ed-rank">{i + 1}</td>
                  <td>{lo.lo_name}</td>
                  <td className="ed-num">{lo.total_activities}</td>
                  <td className="ed-num">{lo.calls}</td>
                  <td className="ed-num">{lo.emails}</td>
                  <td className="ed-num">{lo.texts}</td>
                  <td className="ed-num">{lo.unique_leads}</td>
                </tr>
              ))}
              {leaderboard.length === 0 && (
                <tr><td colSpan="7" className="ed-no-data">No data yet</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Activity Feed */}
        <div className="ed-feed-card">
          <h3>Recent Activity</h3>
          <div className="ed-feed">
            {activityFeed.map((a, i) => (
              <div key={i} className="ed-feed-item">
                <span className={`ed-feed-badge ed-badge-${(a.type || '').toLowerCase()}`}>
                  {a.type}
                </span>
                <div className="ed-feed-content">
                  <strong>{a.lead_name || 'Unknown'}</strong>
                  <span className="ed-feed-text">{a.content}</span>
                  <span className="ed-feed-meta">
                    {a.user_name} &middot; {a.timestamp ? new Date(a.timestamp).toLocaleString() : ''}
                  </span>
                </div>
              </div>
            ))}
            {activityFeed.length === 0 && (
              <div className="ed-no-data">No recent activity</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default EngagementDashboard;
