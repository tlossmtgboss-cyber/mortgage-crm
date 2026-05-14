import React from 'react';
import { useNavigate } from 'react-router-dom';
import OnboardingWizard from '../components/OnboardingWizard';
import './Onboarding.css';
import { getUserData, setTokens } from '../utils/tokenStore';

const Onboarding = () => {
  const navigate = useNavigate();

  const handleOnboardingComplete = async () => {
    // Update localStorage to mark onboarding as completed
    try {
      const user = getUserData();
      if (user) {
        user.onboarding_completed = true;
        await setTokens({ user_data: user });
      }
    } catch (error) {
      console.error('Error updating user data:', error);
    }

    // Navigate to dashboard
    navigate('/dashboard');
  };

  const handleOnboardingSkip = async () => {
    // Mark as completed when skipped
    try {
      const user = getUserData();
      if (user) {
        user.onboarding_completed = true;
        await setTokens({ user_data: user });
      }
    } catch (error) {
      console.error('Error updating user data:', error);
    }

    // Navigate to dashboard
    navigate('/dashboard');
  };

  return (
    <div className="onboarding-page">
      <OnboardingWizard
        onComplete={handleOnboardingComplete}
        onSkip={handleOnboardingSkip}
      />
    </div>
  );
};

export default Onboarding;
