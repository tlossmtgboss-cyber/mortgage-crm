import React, { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area
} from 'recharts';
import './MarketDashboard.css';

// Generate simulated MBS price history
function generateMBSHistory() {
  const data = [];
  const now = new Date();
  let price = 100.5;

  for (let i = 30; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);

    // Simulate price movement
    price += (Math.random() - 0.48) * 0.15;
    price = Math.max(98, Math.min(102, price));

    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      price: parseFloat(price.toFixed(3)),
      volume: Math.floor(Math.random() * 1000) + 500
    });
  }

  return data;
}

// Generate treasury yield history
function generateTreasuryHistory() {
  const data = [];
  const now = new Date();
  let yield10yr = 4.25;

  for (let i = 30; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);

    yield10yr += (Math.random() - 0.5) * 0.03;
    yield10yr = Math.max(3.8, Math.min(4.8, yield10yr));

    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      yield: parseFloat(yield10yr.toFixed(3))
    });
  }

  return data;
}

function MarketDashboard() {
  const [mbsData, setMbsData] = useState([]);
  const [treasuryData, setTreasuryData] = useState([]);
  const [currentPrices, setCurrentPrices] = useState({
    mbs55: 100.98,
    mbs50: 99.44,
    mbs60: 102.21,
    treasury10yr: 4.067,
    treasury2yr: 3.504,
    treasury30yr: 4.722
  });
  const [lastUpdate, setLastUpdate] = useState(new Date());

  useEffect(() => {
    // Initial data
    setMbsData(generateMBSHistory());
    setTreasuryData(generateTreasuryHistory());

    // Simulate real-time updates every 5 seconds
    const interval = setInterval(() => {
      setCurrentPrices(prev => ({
        mbs55: parseFloat((prev.mbs55 + (Math.random() - 0.5) * 0.05).toFixed(2)),
        mbs50: parseFloat((prev.mbs50 + (Math.random() - 0.5) * 0.05).toFixed(2)),
        mbs60: parseFloat((prev.mbs60 + (Math.random() - 0.5) * 0.05).toFixed(2)),
        treasury10yr: parseFloat((prev.treasury10yr + (Math.random() - 0.5) * 0.01).toFixed(3)),
        treasury2yr: parseFloat((prev.treasury2yr + (Math.random() - 0.5) * 0.01).toFixed(3)),
        treasury30yr: parseFloat((prev.treasury30yr + (Math.random() - 0.5) * 0.01).toFixed(3))
      }));
      setLastUpdate(new Date());
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const getChangeColor = (value) => {
    if (value > 0) return 'positive';
    if (value < 0) return 'negative';
    return 'neutral';
  };

  const formatChange = (current, baseline) => {
    const change = current - baseline;
    const sign = change >= 0 ? '+' : '';
    return `${sign}${change.toFixed(2)}`;
  };

  return (
    <div className="market-dashboard-page">
      {/* Header */}
      <div className="market-header">
        <div className="header-left">
          <h1>Market Dashboard</h1>
          <span className="last-update">
            Last Update: {lastUpdate.toLocaleTimeString()}
          </span>
        </div>
        <div className="header-right">
          <span className="market-status open">Market Open</span>
        </div>
      </div>

      <div className="market-content">
        {/* Main Chart */}
        <div className="chart-section">
          <div className="chart-card main-chart">
            <div className="chart-header">
              <h2>30YR UMBS 5.5</h2>
              <div className="current-price">
                <span className="price">{currentPrices.mbs55}</span>
                <span className={`change ${getChangeColor(currentPrices.mbs55 - 100.89)}`}>
                  ({formatChange(currentPrices.mbs55, 100.89)})
                </span>
              </div>
            </div>
            <div className="chart-info">
              <span>PREV: 100.89</span>
              <span>OPEN: 100.97</span>
              <span>LOW: 100.95</span>
              <span>HIGH: 101.03</span>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={mbsData}>
                  <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00d4aa" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#00d4aa" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="date" stroke="#666" fontSize={10} />
                  <YAxis domain={['auto', 'auto']} stroke="#666" fontSize={10} />
                  <Tooltip
                    contentStyle={{ background: '#1a1a1a', border: '1px solid #333' }}
                    labelStyle={{ color: '#fff' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="price"
                    stroke="#00d4aa"
                    fillOpacity={1}
                    fill="url(#colorPrice)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="right-panel">
          {/* MBS Pricing */}
          <div className="pricing-card">
            <h3>MBS Pricing</h3>
            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Coupon</th>
                  <th>Price</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>UMBS 4.5</td>
                  <td>97.46</td>
                  <td className="positive">+0.17</td>
                </tr>
                <tr className="highlighted">
                  <td>UMBS 5.0</td>
                  <td>{currentPrices.mbs50}</td>
                  <td className={getChangeColor(currentPrices.mbs50 - 99.33)}>
                    {formatChange(currentPrices.mbs50, 99.33)}
                  </td>
                </tr>
                <tr className="current">
                  <td>UMBS 5.5</td>
                  <td>{currentPrices.mbs55}</td>
                  <td className={getChangeColor(currentPrices.mbs55 - 100.89)}>
                    {formatChange(currentPrices.mbs55, 100.89)}
                  </td>
                </tr>
                <tr>
                  <td>UMBS 6.0</td>
                  <td>{currentPrices.mbs60}</td>
                  <td className={getChangeColor(currentPrices.mbs60 - 102.17)}>
                    {formatChange(currentPrices.mbs60, 102.17)}
                  </td>
                </tr>
                <tr>
                  <td>UMBS 6.5</td>
                  <td>103.52</td>
                  <td className="negative">-0.07</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Treasury Yields */}
          <div className="pricing-card">
            <h3>Treasury Yields</h3>
            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Term</th>
                  <th>Yield</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>2 YR</td>
                  <td>{currentPrices.treasury2yr}%</td>
                  <td className="negative">-0.032</td>
                </tr>
                <tr>
                  <td>5 YR</td>
                  <td>3.618%</td>
                  <td className="negative">-0.032</td>
                </tr>
                <tr className="highlighted">
                  <td>10 YR</td>
                  <td>{currentPrices.treasury10yr}%</td>
                  <td className="negative">-0.017</td>
                </tr>
                <tr>
                  <td>30 YR</td>
                  <td>{currentPrices.treasury30yr}%</td>
                  <td className="negative">-0.004</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="bottom-section">
          {/* Mortgage Rates */}
          <div className="rates-card">
            <h3>Mortgage Rates</h3>
            <table className="rates-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Rate</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>30 Yr. Fixed</td>
                  <td>6.36%</td>
                  <td className="neutral">+0.00%</td>
                </tr>
                <tr>
                  <td>15 Yr. Fixed</td>
                  <td>5.85%</td>
                  <td className="neutral">+0.00%</td>
                </tr>
                <tr>
                  <td>30 Yr. FHA</td>
                  <td>5.98%</td>
                  <td className="negative">-0.01%</td>
                </tr>
                <tr>
                  <td>30 Yr. Jumbo</td>
                  <td>6.43%</td>
                  <td className="negative">-0.01%</td>
                </tr>
                <tr>
                  <td>7/6 SOFR ARM</td>
                  <td>6.05%</td>
                  <td className="positive">+0.02%</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Economic Calendar */}
          <div className="calendar-card">
            <h3>Economic Calendar</h3>
            <div className="calendar-date">
              Friday, November 21st
            </div>
            <div className="calendar-events">
              <div className="event">
                <span className="time">7:30 am</span>
                <span className="name">Fed Williams Speech</span>
              </div>
              <div className="event">
                <span className="time">8:30 am</span>
                <span className="name">Fed Barr Speech</span>
              </div>
              <div className="event">
                <span className="time">8:45 am</span>
                <span className="name">Fed Jefferson Speech</span>
              </div>
              <div className="event">
                <span className="time">9:00 am</span>
                <span className="name">Fed Logan Speech</span>
              </div>
              <div className="event">
                <span className="time">9:45 am</span>
                <span className="name">S&P PMI Flash</span>
                <span className="impact high">HIGH</span>
              </div>
              <div className="event">
                <span className="time">10:00 am</span>
                <span className="name">Consumer Sentiment</span>
                <span className="impact high">HIGH</span>
              </div>
            </div>
          </div>

          {/* Market Indicators */}
          <div className="indicators-card">
            <h3>Market Indicators</h3>
            <div className="indicator">
              <span className="label">Volatility</span>
              <span className="value normal">Normal</span>
            </div>
            <div className="indicator">
              <span className="label">Market Trend</span>
              <span className="value stable">Stable</span>
            </div>
            <div className="indicator">
              <span className="label">Lock Recommendation</span>
              <span className="value caution">Cautious Float</span>
            </div>
            <div className="indicator">
              <span className="label">2s/10s Spread</span>
              <span className="value">0.562</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MarketDashboard;
