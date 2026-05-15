import React, { useState, useEffect, useRef } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts';
import { profitabilityAPI } from '../services/api';
import './CostToCloseChart.css';

const CostToCloseChart = ({
  refreshInterval = 60000, // 1 minute default
  showLiveIndicator = true,
  height = 300
}) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentValue, setCurrentValue] = useState(null);
  const [trend, setTrend] = useState(null); // 'up', 'down', 'stable'
  const intervalRef = useRef(null);

  // Format time for display
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  // Format date for tooltip
  const formatTooltipDate = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Format currency
  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(value);
  };

  // Fetch cost to close data
  const fetchData = async () => {
    try {
      // Get current metrics
      const metrics = await profitabilityAPI.getMetrics();
      const costPerLoan = metrics.cost_per_loan || 0;

      const timestamp = Date.now();

      setData(prevData => {
        const newData = [...prevData, {
          timestamp,
          time: formatTime(timestamp),
          value: costPerLoan
        }];

        // Keep last 60 data points (1 hour at 1-min intervals)
        if (newData.length > 60) {
          return newData.slice(-60);
        }
        return newData;
      });

      // Calculate trend
      if (data.length > 0) {
        const lastValue = data[data.length - 1]?.value || 0;
        if (costPerLoan > lastValue) {
          setTrend('up');
        } else if (costPerLoan < lastValue) {
          setTrend('down');
        } else {
          setTrend('stable');
        }
      }

      setCurrentValue(costPerLoan);
      setLoading(false);
    } catch (err) {
      console.error('Failed to fetch cost to close:', err);
      setLoading(false);
    }
  };

  // Initialize and set up polling
  useEffect(() => {
    // Initial fetch
    fetchData();

    // Set up interval for real-time updates
    intervalRef.current = setInterval(fetchData, refreshInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [refreshInterval]);

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const dataPoint = payload[0].payload;
      return (
        <div className="ctc-tooltip">
          <p className="ctc-tooltip-date">{formatTooltipDate(dataPoint.timestamp)}</p>
          <p className="ctc-tooltip-value">
            Cost: <strong>{formatCurrency(payload[0].value)}</strong>
          </p>
        </div>
      );
    }
    return null;
  };

  // Calculate Y-axis domain with padding
  const getYDomain = () => {
    if (data.length === 0) return [0, 10000];

    const values = data.map(d => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = (max - min) * 0.1 || 100;

    return [
      Math.max(0, min - padding),
      max + padding
    ];
  };

  if (loading && data.length === 0) {
    return (
      <div className="ctc-chart-container" style={{ height }}>
        <div className="ctc-loading">
          <div className="ctc-loading-spinner"></div>
          <p>Loading cost data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ctc-chart-container">
      <div className="ctc-header">
        <div className="ctc-title-section">
          <h3>Cost to Close</h3>
          {showLiveIndicator && (
            <span className="ctc-live-indicator">
              <span className="ctc-live-dot"></span>
              LIVE
            </span>
          )}
        </div>
        {currentValue !== null && (
          <div className="ctc-current-value">
            <span className={`ctc-value ${trend}`}>
              {formatCurrency(currentValue)}
            </span>
            {trend && trend !== 'stable' && (
              <span className={`ctc-trend-arrow ${trend}`}>
                {trend === 'up' ? '↑' : '↓'}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="ctc-chart" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2D7A52" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#2D7A52" stopOpacity={0.05}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: '#6b7280' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e7eb' }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={getYDomain()}
              tick={{ fontSize: 11, fill: '#6b7280' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${(value/1000).toFixed(1)}k`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#2D7A52"
              strokeWidth={2}
              fill="url(#costGradient)"
              animationDuration={300}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="ctc-footer">
        <span className="ctc-update-info">
          Updates every {refreshInterval / 1000}s • {data.length} data points
        </span>
      </div>
    </div>
  );
};

export default CostToCloseChart;
