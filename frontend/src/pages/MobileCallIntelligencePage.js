/**
 * MobileCallIntelligencePage
 *
 * Full-screen page wrapper for mobile call intelligence.
 * Renders MobileCallIntelligencePanel with navigation handling.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import MobileCallIntelligencePanel from '../components/MobileCallIntelligencePanel';

const MobileCallIntelligencePage = () => {
  const navigate = useNavigate();

  const handleClose = () => {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate('/');
    }
  };

  return (
    <MobileCallIntelligencePanel
      onClose={handleClose}
      initialContext={{ source: 'mobile_app' }}
    />
  );
};

export default MobileCallIntelligencePage;
