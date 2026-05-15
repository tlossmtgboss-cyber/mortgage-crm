import React, { useState } from 'react';
import './DISCWheel.css';

/**
 * Zone information for the behavioral pattern view wheel
 */
const ZONES = {
  1: { name: 'Implementor', color: '#DC2626', primary: 'D', angle: 337.5 },
  2: { name: 'Conductor', color: '#EA580C', primary: 'D/I', angle: 22.5 },
  3: { name: 'Persuader', color: '#F59E0B', primary: 'I/D', angle: 67.5 },
  4: { name: 'Promoter', color: '#FBBF24', primary: 'I', angle: 112.5 },
  5: { name: 'Relater', color: '#84CC16', primary: 'S/I', angle: 157.5 },
  6: { name: 'Supporter', color: '#22C55E', primary: 'S', angle: 202.5 },
  7: { name: 'Coordinator', color: '#14B8A6', primary: 'C/S', angle: 247.5 },
  8: { name: 'Analyzer', color: '#3B82F6', primary: 'C', angle: 292.5 }
};

/**
 * DISCWheel Component
 * SVG-based behavioral pattern view wheel with 8 zones
 */
function DISCWheel({
  zone = 1,
  position = 1,
  zoneName = '',
  size = 280,
  showLabels = true,
  interactive = true
}) {
  const [hoveredZone, setHoveredZone] = useState(null);

  const center = size / 2;
  const outerRadius = (size - 40) / 2;
  const innerRadius = outerRadius * 0.2;
  const markerRadius = outerRadius * 0.6;

  // Calculate marker position based on zone and position
  const markerAngle = calculateMarkerAngle(zone, position);
  const markerX = center + markerRadius * Math.cos((markerAngle - 90) * Math.PI / 180);
  const markerY = center + markerRadius * Math.sin((markerAngle - 90) * Math.PI / 180);

  // Generate zone arcs
  const zones = Object.entries(ZONES).map(([zoneNum, zoneInfo]) => {
    const startAngle = zoneInfo.angle - 22.5;
    const endAngle = zoneInfo.angle + 22.5;

    return {
      ...zoneInfo,
      zoneNum: parseInt(zoneNum),
      path: describeArc(center, center, outerRadius, startAngle, endAngle)
    };
  });

  return (
    <div className="disc-wheel-container" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="disc-wheel-svg"
      >
        {/* Background circle */}
        <circle
          cx={center}
          cy={center}
          r={outerRadius}
          fill="#f9fafb"
          stroke="#e5e7eb"
          strokeWidth="1"
        />

        {/* Zone segments */}
        {zones.map((zoneData) => (
          <g key={zoneData.zoneNum}>
            <path
              d={zoneData.path}
              fill={zoneData.zoneNum === zone ? zoneData.color : `${zoneData.color}30`}
              stroke="#fff"
              strokeWidth="2"
              className={`disc-wheel-zone ${interactive ? 'interactive' : ''}`}
              onMouseEnter={() => interactive && setHoveredZone(zoneData.zoneNum)}
              onMouseLeave={() => interactive && setHoveredZone(null)}
              style={{
                opacity: hoveredZone === zoneData.zoneNum ? 1 : hoveredZone ? 0.5 : 1
              }}
            />
          </g>
        ))}

        {/* Inner circle */}
        <circle
          cx={center}
          cy={center}
          r={innerRadius}
          fill="#fff"
          stroke="#e5e7eb"
          strokeWidth="1"
        />

        {/* Grid circles */}
        {[0.33, 0.66].map((pct, i) => (
          <circle
            key={i}
            cx={center}
            cy={center}
            r={innerRadius + (outerRadius - innerRadius) * pct}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
        ))}

        {/* Zone divider lines */}
        {Object.values(ZONES).map((zoneInfo, i) => {
          const lineAngle = (zoneInfo.angle - 22.5 - 90) * Math.PI / 180;
          const x2 = center + outerRadius * Math.cos(lineAngle);
          const y2 = center + outerRadius * Math.sin(lineAngle);
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={x2}
              y2={y2}
              stroke="#e5e7eb"
              strokeWidth="1"
            />
          );
        })}

        {/* Zone labels */}
        {showLabels && zones.map((zoneData) => {
          const labelRadius = outerRadius * 0.85;
          const labelAngle = (zoneData.angle - 90) * Math.PI / 180;
          const x = center + labelRadius * Math.cos(labelAngle);
          const y = center + labelRadius * Math.sin(labelAngle);

          return (
            <text
              key={zoneData.zoneNum}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="disc-wheel-zone-label"
              fill={zoneData.zoneNum === zone ? '#fff' : '#6b7280'}
              fontSize="10"
              fontWeight="600"
            >
              {zoneData.name}
            </text>
          );
        })}

        {/* Candidate marker */}
        <g className="disc-wheel-marker">
          <circle
            cx={markerX}
            cy={markerY}
            r={12}
            fill={ZONES[zone]?.color || '#374151'}
            stroke="#fff"
            strokeWidth="3"
            className="disc-wheel-marker-circle"
          />
          <circle
            cx={markerX}
            cy={markerY}
            r={5}
            fill="#fff"
          />
        </g>

        {/* Dimension labels at edges */}
        <text x={center} y={18} textAnchor="middle" className="disc-wheel-dim-label" fill="#DC2626">D</text>
        <text x={size - 18} y={center} textAnchor="middle" className="disc-wheel-dim-label" fill="#F59E0B">I</text>
        <text x={center} y={size - 8} textAnchor="middle" className="disc-wheel-dim-label" fill="#2D7A52">S</text>
        <text x={18} y={center} textAnchor="middle" className="disc-wheel-dim-label" fill="#3B82F6">C</text>
      </svg>

      {/* Zone info panel */}
      <div className="disc-wheel-info">
        <span
          className="disc-wheel-zone-name"
          style={{ color: ZONES[hoveredZone || zone]?.color }}
        >
          {ZONES[hoveredZone || zone]?.name || zoneName}
        </span>
        <span className="disc-wheel-zone-primary">
          Primary: {ZONES[hoveredZone || zone]?.primary}
        </span>
      </div>
    </div>
  );
}

/**
 * Calculate marker angle based on zone (1-8) and position (1-81)
 */
function calculateMarkerAngle(zone, position) {
  // Base angle for the zone (center of zone)
  const zoneInfo = ZONES[zone];
  if (!zoneInfo) return 0;

  // Position within zone (1-81 distributed across 8 zones, ~10 positions per zone)
  const positionOffset = ((position % 10) - 5) * 2; // -8 to +8 degrees

  return zoneInfo.angle + positionOffset;
}

/**
 * Generate SVG arc path
 */
function describeArc(x, y, radius, startAngle, endAngle) {
  const start = polarToCartesian(x, y, radius, endAngle);
  const end = polarToCartesian(x, y, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

  return [
    "M", x, y,
    "L", start.x, start.y,
    "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y,
    "Z"
  ].join(" ");
}

function polarToCartesian(centerX, centerY, radius, angleInDegrees) {
  const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
  return {
    x: centerX + radius * Math.cos(angleInRadians),
    y: centerY + radius * Math.sin(angleInRadians)
  };
}

/**
 * Mini wheel for compact display
 */
export function DISCWheelMini({ zone = 1, size = 80 }) {
  const center = size / 2;
  const radius = (size - 8) / 2;

  return (
    <div className="disc-wheel-mini">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill={ZONES[zone]?.color || '#e5e7eb'}
        />
        <text
          x={center}
          y={center}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#fff"
          fontSize="10"
          fontWeight="700"
        >
          {ZONES[zone]?.name?.slice(0, 3).toUpperCase() || '?'}
        </text>
      </svg>
    </div>
  );
}

export default DISCWheel;
