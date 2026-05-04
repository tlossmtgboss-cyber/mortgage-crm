/**
 * Click-to-Dial Button Component
 * Opens Teams to call the given phone number.
 */

import React from 'react';
import { Phone } from 'lucide-react';

const ClickToDialButton = ({
  contactName,
  phone,
  variant = 'primary',
  size = 'md',
  className = ''
}) => {
  if (!phone) {
    return null;
  }

  const handleClick = () => {
    const cleanPhone = phone.replace(/[^\d+]/g, '');
    const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;
    window.open(`https://teams.microsoft.com/l/call/0/0?users=4:${encodeURIComponent(dialNumber)}`, '_blank');
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
      className={`
        inline-flex items-center justify-center rounded-md transition-colors
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
        ${sizeClasses[size]}
        ${variantClasses[variant]}
        ${className}
      `}
      title={`Call ${contactName || phone} via Teams`}
    >
      <Phone className={`${iconSize[size]} ${variant !== 'icon' ? 'mr-1.5' : ''}`} />
      {variant !== 'icon' && 'Call'}
    </button>
  );
};

export default ClickToDialButton;
