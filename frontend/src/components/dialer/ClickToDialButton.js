/**
 * Click-to-Dial Button Component
 * Displays a call button that opens the click-to-dial modal
 */

import React, { useState } from 'react';
import { Phone } from 'lucide-react';
import ClickToDialModal from './ClickToDialModal';

/**
 * @param {Object} props
 * @param {string} props.contactId - Contact ID
 * @param {string} props.contactName - Contact's name
 * @param {string} props.phone - Phone number to call
 * @param {string} [props.loanId] - Associated loan ID
 * @param {string} [props.leadId] - Associated lead ID
 * @param {string} [props.taskId] - Associated task ID
 * @param {string} [props.context] - Call context (e.g., "Follow up on application")
 * @param {string} [props.variant] - Button variant: 'primary', 'secondary', 'icon'
 * @param {string} [props.size] - Button size: 'sm', 'md', 'lg'
 * @param {string} [props.className] - Additional CSS classes
 */
const ClickToDialButton = ({
  contactId,
  contactName,
  phone,
  loanId,
  leadId,
  taskId,
  context,
  variant = 'primary',
  size = 'md',
  className = ''
}) => {
  const [showModal, setShowModal] = useState(false);

  // Don't render if no phone number
  if (!phone) {
    return null;
  }

  // Size classes
  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1.5 text-sm',
    lg: 'px-4 py-2 text-base'
  };

  // Variant classes
  const variantClasses = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300',
    icon: 'bg-transparent text-blue-600 hover:bg-blue-50 p-2'
  };

  // Icon size based on button size
  const iconSize = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5'
  };

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className={`
          inline-flex items-center justify-center rounded-md transition-colors
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
          ${sizeClasses[size]}
          ${variantClasses[variant]}
          ${className}
        `}
        title={`Call ${contactName}`}
      >
        <Phone className={`${iconSize[size]} ${variant !== 'icon' ? 'mr-1.5' : ''}`} />
        {variant !== 'icon' && 'Call'}
      </button>

      {showModal && (
        <ClickToDialModal
          contactId={contactId}
          contactName={contactName}
          phone={phone}
          loanId={loanId}
          leadId={leadId}
          taskId={taskId}
          context={context}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
};

export default ClickToDialButton;
