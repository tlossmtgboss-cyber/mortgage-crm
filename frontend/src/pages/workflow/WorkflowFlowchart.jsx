import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import FlowchartCanvas from './FlowchartCanvas';
import FlowchartToolbar from './FlowchartToolbar';
import NodeDetailDrawer from './NodeDetailDrawer';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';

export default function WorkflowFlowchart() {
  const { workflowKey } = useParams();
  const { onRefresh } = useOutletContext();
  const [graph, setGraph] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [placingNodeType, setPlacingNodeType] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [loading, setLoading] = useState(true);
  const positionTimer = useRef(null);

  const fetchGraph = useCallback(async () => {
    try {
      const { data } = await workflowGraphApi.getGraph(workflowKey);
      setGraph(data.definition);
      setNodes(data.nodes);
      setEdges(data.edges);
    } catch (err) {
      toast.error('Failed to load workflow');
    } finally {
      setLoading(false);
    }
  }, [workflowKey]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  const handleNodeDrag = useCallback((nodeId, x, y) => {
    setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, x, y } : n));
    clearTimeout(positionTimer.current);
    positionTimer.current = setTimeout(() => {
      workflowGraphApi.bulkUpdatePositions(workflowKey,
        [{ id: nodeId, x, y }]
      ).catch(() => {});
    }, 500);
  }, [workflowKey]);

  const handlePlaceNode = async ({ x, y }) => {
    if (!placingNodeType) return;
    try {
      await workflowGraphApi.addNode(workflowKey, {
        type: placingNodeType,
        label: `New ${placingNodeType.charAt(0).toUpperCase() + placingNodeType.slice(1)}`,
        x, y,
      });
      setPlacingNodeType(null);
      fetchGraph();
    } catch (err) {
      toast.error('Failed to add node');
    }
  };

  const handleNodeUpdate = async (nodeId, updates) => {
    try {
      await workflowGraphApi.updateNode(workflowKey, nodeId, updates);
      setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, ...updates } : n));
    } catch (err) {
      toast.error('Failed to update node');
    }
  };

  const handleNodeDelete = async (nodeId) => {
    try {
      await workflowGraphApi.deleteNode(workflowKey, nodeId);
      setSelectedId(null);
      fetchGraph();
      onRefresh();
    } catch (err) {
      toast.error('Failed to delete node');
    }
  };

  const selectedNode = nodes.find(n => n.id === selectedId);
  const totalLeads = nodes.reduce((sum, n) => sum + (n.lead_count || 0), 0);

  if (loading) {
    return <div className="wf-loading">Loading flowchart...</div>;
  }

  return (
    <div className="wf-flowchart">
      <FlowchartToolbar
        workflowName={graph?.name || workflowKey}
        totalLeads={totalLeads}
        zoom={zoom}
        onZoomIn={() => setZoom(z => Math.min(2, z + 0.1))}
        onZoomOut={() => setZoom(z => Math.max(0.3, z - 0.1))}
        onZoomReset={() => setZoom(1)}
        placingNodeType={placingNodeType}
        onSetPlacingNodeType={setPlacingNodeType}
        simulating={simulating}
        onSimulate={() => setSimulating(s => !s)}
      />

      <div className="wf-flowchart-body">
        <FlowchartCanvas
          nodes={nodes}
          edges={edges}
          selectedId={selectedId}
          onNodeSelect={setSelectedId}
          onNodeDrag={handleNodeDrag}
          onCanvasClick={() => setSelectedId(null)}
          placingNodeType={placingNodeType}
          onPlaceNode={handlePlaceNode}
        />

        {selectedNode && (
          <NodeDetailDrawer
            workflowKey={workflowKey}
            node={selectedNode}
            onUpdate={(updates) => handleNodeUpdate(selectedId, updates)}
            onDelete={() => handleNodeDelete(selectedId)}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}
