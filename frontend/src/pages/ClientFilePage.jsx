import { useParams } from 'react-router-dom';
import { getCurrentUserId } from '../utils/auth';
import { ClientFileView } from '../client-file';

export default function ClientFilePage() {
  const { uuid } = useParams();
  const currentUserId = getCurrentUserId();

  if (!currentUserId) return null;

  return (
    <ClientFileView
      clientFileId={uuid}
      currentUserId={String(currentUserId)}
    />
  );
}
