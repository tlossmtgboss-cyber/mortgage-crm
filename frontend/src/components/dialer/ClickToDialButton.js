import React, { useState } from 'react';
import { Phone } from 'lucide-react';
import { clickToDial } from '../../utils/clickToDial';

const ClickToDialButton = ({
  contactName,
  phone,
  leadId = null,
  loanId = null,
  variant = 'primary',
  size = 'md',
  className = ''
}) => {
  const [calling, setCalling] = useState(false);

  if (!phone) {
    return null;
  }

  const handleClick = async () => {
    if (calling) return;
    setCalling(true);
    await clickToDial(phone, { contactName, leadId, loanId });
    setTimeout(() => setCalling(false), 3000);
  };

  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1.5 text-sm',
    lg: 'px-4 py-2 text-base'
  };

  const variantClasses = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300',
    icon: 'bg-transparent text-blue-600 hover:bg-blue-50 p-2'
  };

  const iconSize = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5'
  };

  return (
    <button
      onClick={handleClick}
      disabled={calling}
      className={`
        inline-flex items-center justify-center rounded-md transition-colors
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
        ${calling ? 'opacity-60 cursor-not-allowed' : ''}
        ${sizeClasses[size]}
        ${variantClasses[variant]}
        ${className}
      `}
      title={`Call ${contactName || phone}`}
    >
      <Phone className={`${iconSize[size]} ${variant !== 'icon' ? 'mr-1.5' : ''}`} />
      {variant !== 'icon' && (calling ? 'Calling...' : 'Call')}
    </button>
  );
};

export default ClickToDialButton;
