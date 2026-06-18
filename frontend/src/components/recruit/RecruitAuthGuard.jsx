import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useRecruitPlatform } from '../../contexts/RecruitPlatformContext';

export default function RecruitAuthGuard({ children }) {
  const { isAuthenticated, isPlatformAdmin } = useRecruitPlatform();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/recruit/login" state={{ from: location }} replace />;
  }

  if (location.pathname === '/recruit/license-manager' && !isPlatformAdmin) {
    return <Navigate to="/recruit/dashboard" replace />;
  }

  return children;
}
