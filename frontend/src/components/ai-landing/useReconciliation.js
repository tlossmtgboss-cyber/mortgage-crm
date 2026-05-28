import { useState } from 'react';
import { reconciliationAPI } from '../../services/api';
import { toast } from '../../utils/toast';

export function useReconciliation() {
  const [reconciliationItems, setReconciliationItems] = useState([]);
  const [selectedReconciliationItem, setSelectedReconciliationItem] = useState(null);
  const [showReconciliationSidebar, setShowReconciliationSidebar] = useState(false);
  const [reconciliationLoading, setReconciliationLoading] = useState(false);
  const [reconciliationTab, setReconciliationTab] = useState('new');
  const [reconciliationCounts, setReconciliationCounts] = useState({ new: 0, auto: 0, pending: 0, completed: 0 });
  const [autoProcessEnabled, setAutoProcessEnabled] = useState(false);

  const fetchReconciliationItems = async (status = null) => {
    setReconciliationLoading(true);
    try {
      const tabStatus = status || reconciliationTab;
      const response = await reconciliationAPI.getPending(tabStatus === 'new' ? 'pending' : tabStatus);
      const items = response.items || [];
      setReconciliationItems(items);
      if (items.length > 0) {
        setSelectedReconciliationItem(items[0]);
      } else {
        setSelectedReconciliationItem(null);
      }

      setReconciliationCounts(prev => ({
        ...prev,
        [tabStatus]: items.length
      }));
    } catch (error) {
      console.error('Error fetching reconciliation items:', error);
      setReconciliationItems([]);
    } finally {
      setReconciliationLoading(false);
    }
  };

  const openReconciliationSidebar = async (setShowRightSidebar) => {
    setShowReconciliationSidebar(true);
    setShowRightSidebar(false);
    await fetchReconciliationItems();
  };

  const handleReconciliationApprove = async (item, updateStatusTo = null) => {
    try {
      const payload = {
        extracted_data_id: item.id,
        ...(updateStatusTo && { update_status_to: updateStatusTo })
      };
      await reconciliationAPI.approve(payload);
      const newItems = reconciliationItems.filter(i => i.id !== item.id);
      setReconciliationItems(newItems);
      if (newItems.length > 0) {
        setSelectedReconciliationItem(newItems[0]);
      } else {
        setSelectedReconciliationItem(null);
      }
    } catch (error) {
      console.error('Error approving reconciliation:', error);
      toast.error('Failed to approve: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleReconciliationReject = async (item, reason = 'User rejected') => {
    try {
      await reconciliationAPI.reject({ extracted_data_id: item.id, reason });
      const newItems = reconciliationItems.filter(i => i.id !== item.id);
      setReconciliationItems(newItems);
      if (newItems.length > 0) {
        setSelectedReconciliationItem(newItems[0]);
      } else {
        setSelectedReconciliationItem(null);
      }
    } catch (error) {
      console.error('Error rejecting reconciliation:', error);
      toast.error('Failed to reject: ' + (error.response?.data?.detail || error.message));
    }
  };

  return {
    reconciliationItems,
    selectedReconciliationItem,
    setSelectedReconciliationItem,
    showReconciliationSidebar,
    setShowReconciliationSidebar,
    reconciliationLoading,
    reconciliationTab,
    setReconciliationTab,
    reconciliationCounts,
    autoProcessEnabled,
    setAutoProcessEnabled,
    fetchReconciliationItems,
    openReconciliationSidebar,
    handleReconciliationApprove,
    handleReconciliationReject
  };
}
