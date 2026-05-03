import React from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const POSEntryPage: React.FC = () => {
  const [searchParams] = useSearchParams();

  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;
  const borrowerName = searchParams.get('name') || 'there';
  const initials = searchParams.get('initials') || '';

  return (
    <POSContainer
      loanId={loanId}
      borrowerName={borrowerName}
      userInitials={initials}
    />
  );
};

export default POSEntryPage;
