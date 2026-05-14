import React from 'react';
import { onboardingAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import { FALLBACK_MILESTONES } from './fallbackData';

const ProcessUploadStep = ({
  formData, setFormData,
  isProcessing, setIsProcessing,
  setCurrentStep,
  handleFileSelect, removeFile, formatFileSize,
  handleDragOver, handleDrop,
  updateField
}) => {
  const handleAIProcessing = async () => {
    setIsProcessing(true);

    try {
      const parseResult = await onboardingAPI.parseDocumentsUpload(formData.sopFiles);

      const generatedMilestones = parseResult.milestones.map((milestone) => {
        const milestoneTasks = parseResult.tasks
          .filter(task => task.milestone_id === milestone.id)
          .map(task => {
            const role = parseResult.roles.find(r => r.id === task.role_id);
            return {
              name: task.task_name,
              owner: role?.role_title || 'Unassigned',
              sla: task.sla || 24,
              slaUnit: task.sla_unit || 'hours',
              aiAuto: task.ai_automatable || false
            };
          });

        return {
          name: milestone.name,
          tasks: milestoneTasks
        };
      });

      const totalTasks = parseResult.tasks?.length || 0;
      const totalMilestones = parseResult.milestones?.length || 0;
      const totalRoles = parseResult.roles?.length || 0;

      const updatedFormData = {
        ...formData,
        milestones: generatedMilestones,
        extractedRoles: parseResult.roles || [],
        extractedTasks: parseResult.tasks || [],
        extractedMilestones: parseResult.milestones || [],
        processTree: {
          generated: true,
          milestones: totalMilestones,
          tasks: totalTasks,
          roles: totalRoles
        }
      };

      setFormData(updatedFormData);

      try {
        localStorage.setItem('onboarding_process_data', JSON.stringify({
          extractedRoles: parseResult.roles,
          extractedTasks: parseResult.tasks,
          extractedMilestones: parseResult.milestones,
          processTree: updatedFormData.processTree
        }));
      } catch (error) {
        console.error('Failed to persist to localStorage:', error);
      }

      setIsProcessing(false);
      setCurrentStep(2);

    } catch (error) {
      console.error('Error parsing documents:', error);
      setIsProcessing(false);
      toast.error('Failed to parse documents. Please try again.');

      // Fallback to sample data
      const generatedMilestones = FALLBACK_MILESTONES;
      const totalTasks = generatedMilestones.reduce((total, m) => total + m.tasks.length, 0);

      const uniqueRoles = new Set();
      generatedMilestones.forEach(milestone => {
        milestone.tasks.forEach(task => {
          uniqueRoles.add(task.owner);
        });
      });

      const fallbackRoles = Array.from(uniqueRoles).map((roleName, index) => ({
        id: `role-${index + 1}`,
        role_title: roleName,
        role_name: roleName,
        responsibilities: `Handles ${roleName} responsibilities`
      }));

      const fallbackTasks = [];
      generatedMilestones.forEach((milestone, mIndex) => {
        milestone.tasks.forEach((task, tIndex) => {
          const roleObj = fallbackRoles.find(r => r.role_name === task.owner);
          fallbackTasks.push({
            id: `task-${mIndex}-${tIndex}`,
            name: task.name,
            role_id: roleObj?.id,
            milestone_id: `milestone-${mIndex}`,
            sla: task.sla,
            slaUnit: task.slaUnit,
            aiAuto: task.aiAuto
          });
        });
      });

      const fallbackMilestones = generatedMilestones.map((milestone, index) => ({
        id: `milestone-${index}`,
        name: milestone.name,
        order: index + 1
      }));

      setFormData(prevData => ({
        ...prevData,
        milestones: generatedMilestones,
        extractedRoles: fallbackRoles,
        extractedTasks: fallbackTasks,
        extractedMilestones: fallbackMilestones,
        processTree: {
          generated: true,
          milestones: fallbackMilestones.length,
          tasks: fallbackTasks.length,
          roles: fallbackRoles.length
        }
      }));

      setIsProcessing(false);
    }
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📄</div>
        <h2>Upload Your Process Documents</h2>
        <p className="step-description">Upload your SOPs first - AI will generate ALL tasks and workflows to assign to your team</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Upload Process Documents</label>
          <p className="field-hint">PDFs, DOCX, XLSX, CSV of your SOPs (Lead → Loan → Post-Close)</p>
          <div
            className="file-upload-area"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt"
              onChange={handleFileSelect}
              className="file-input"
              id="sop-upload"
            />
            <label htmlFor="sop-upload" className="file-upload-label">
              <div className="upload-icon">📎</div>
              <div className="upload-text">Click to upload or drag and drop</div>
              <div className="upload-hint">PDF, DOCX, XLSX, CSV, TXT (max 10 files, 50MB each)</div>
            </label>
          </div>

          {formData.sopFiles && formData.sopFiles.length > 0 && (
            <div className="uploaded-files">
              <div className="files-header">
                <h4>{formData.sopFiles.length} file{formData.sopFiles.length !== 1 ? 's' : ''} uploaded</h4>
                <button
                  className="btn-clear-all"
                  onClick={() => updateField('sopFiles', [])}
                >
                  Clear all
                </button>
              </div>
              {formData.sopFiles.map((file, index) => (
                <div key={index} className="file-item">
                  <div className="file-icon">
                    {file.name.endsWith('.pdf') ? '📕' :
                     file.name.endsWith('.docx') || file.name.endsWith('.doc') ? '📘' :
                     file.name.endsWith('.xlsx') || file.name.endsWith('.xls') ? '📗' :
                     file.name.endsWith('.csv') ? '📊' : '📄'}
                  </div>
                  <div className="file-info">
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">{formatFileSize(file.size)}</div>
                  </div>
                  <button
                    className="btn-remove-file"
                    onClick={() => removeFile(index)}
                    title="Remove file"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {formData.sopFiles && formData.sopFiles.length > 0 && !formData.processTree && (
          <div className="ai-processing">
            <button
              className="btn-ai-process"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <>
                  <span className="spinner"></span>
                  Processing...
                </>
              ) : (
                <>🤖 AI: Parse & Generate Process Tree</>
              )}
            </button>
            <p className="processing-hint">
              AI will extract milestones, tasks, and role ownership from your {formData.sopFiles.length} document{formData.sopFiles.length !== 1 ? 's' : ''}
            </p>
          </div>
        )}

        {formData.processTree && (
          <div className="process-tree-preview">
            <h4>✓ Process Tree Generated</h4>
            <div className="preview-stats">
              <div className="stat-item">
                <span className="stat-label">Milestones</span>
                <span className="stat-number">{formData.processTree.milestones}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Tasks</span>
                <span className="stat-number">{formData.processTree.tasks}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Roles</span>
                <span className="stat-number">{formData.processTree.roles}</span>
              </div>
            </div>
            <button
              className="btn-regenerate"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              🔄 Regenerate
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProcessUploadStep;
