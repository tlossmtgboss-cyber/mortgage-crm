import {
  ActionPlansPanel,
  DocumentsPanel,
  FollowUpsPanel,
  InsightsPanel,
  LoanPanel,
  RelationshipsPanel,
  TasksPanel,
} from "./RailPanels";

interface Props {
  clientFileId: string;
}

export function ToolsRail({ clientFileId }: Props) {
  return (
    <div className="pf-cf-rail">
      <LoanPanel clientFileId={clientFileId} />
      <InsightsPanel clientFileId={clientFileId} />
      <FollowUpsPanel clientFileId={clientFileId} />
      <TasksPanel clientFileId={clientFileId} />
      <DocumentsPanel clientFileId={clientFileId} />
      <ActionPlansPanel clientFileId={clientFileId} />
      <RelationshipsPanel clientFileId={clientFileId} />
    </div>
  );
}
