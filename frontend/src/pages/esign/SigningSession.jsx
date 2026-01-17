/**
 * Signing Session Page
 *
 * Borrower-facing page for completing e-signature documents.
 * Token-based authentication (no login required).
 *
 * Features:
 * - PDF viewer with field overlays
 * - Guided field completion
 * - Progress tracking
 * - Signature adoption
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Paper,
  Typography,
  Button,
  LinearProgress,
  Alert,
  CircularProgress,
  Stepper,
  Step,
  StepLabel,
  TextField,
  Checkbox,
  FormControlLabel,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Divider,
  IconButton,
  Tooltip,
  Chip,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  RadioButtonUnchecked as UncheckedIcon,
  NavigateBefore as PrevIcon,
  NavigateNext as NextIcon,
  Draw as SignIcon,
  Done as DoneIcon,
  ZoomIn as ZoomInIcon,
  ZoomOut as ZoomOutIcon,
} from '@mui/icons-material';
import { esignApi, pdfPointsToScreen, pdfSizeToScreen, FIELD_TYPES, SIGNATURE_FONTS } from '../../services/esignApi';
import SignatureAdoptionModal from '../../components/esign/SignatureAdoptionModal';

/**
 * Field input component based on field type
 */
const FieldInput = ({
  field,
  value,
  adoptedSignature,
  onSubmit,
  onRequestSignature,
  disabled,
}) => {
  const [inputValue, setInputValue] = useState(value || '');
  const [checkboxValue, setCheckboxValue] = useState(value === 'true' || value === true);

  const fieldConfig = FIELD_TYPES[field.field_type] || FIELD_TYPES.text;

  const handleSubmit = () => {
    if (field.field_type === 'checkbox') {
      onSubmit(field.id, checkboxValue);
    } else {
      onSubmit(field.id, inputValue);
    }
  };

  // Signature/Initial fields
  if (field.field_type === 'signature' || field.field_type === 'initial') {
    if (!adoptedSignature) {
      return (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            You need to adopt your signature first
          </Typography>
          <Button
            variant="contained"
            startIcon={<SignIcon />}
            onClick={onRequestSignature}
            sx={{ mt: 1 }}
          >
            Adopt Signature
          </Button>
        </Box>
      );
    }

    const font = SIGNATURE_FONTS.find(f => f.id === adoptedSignature.font) || SIGNATURE_FONTS[0];

    return (
      <Box sx={{ textAlign: 'center', py: 2 }}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Click to apply your {field.field_type}
        </Typography>
        <Paper
          elevation={1}
          sx={{
            p: 2,
            my: 2,
            backgroundColor: '#fafafa',
            cursor: disabled ? 'default' : 'pointer',
            '&:hover': disabled ? {} : { backgroundColor: '#f0f0f0' },
          }}
          onClick={() => !disabled && onSubmit(field.id, adoptedSignature.text)}
        >
          <Typography
            sx={{
              fontFamily: font.family,
              fontSize: field.field_type === 'initial' ? '24px' : '32px',
              color: '#1a1a1a',
            }}
          >
            {field.field_type === 'initial'
              ? adoptedSignature.text.split(' ').map(n => n[0]).join('')
              : adoptedSignature.text}
          </Typography>
        </Paper>
        <Button
          variant="contained"
          onClick={() => onSubmit(field.id, adoptedSignature.text)}
          disabled={disabled}
        >
          Apply {field.field_type === 'initial' ? 'Initials' : 'Signature'}
        </Button>
      </Box>
    );
  }

  // Date signed field - auto-populated
  if (field.field_type === 'date_signed') {
    const today = new Date().toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });

    return (
      <Box sx={{ py: 2 }}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Date will be recorded as:
        </Typography>
        <Typography variant="h6" sx={{ my: 1 }}>
          {today}
        </Typography>
        <Button
          variant="contained"
          onClick={() => onSubmit(field.id, today)}
          disabled={disabled}
        >
          Confirm Date
        </Button>
      </Box>
    );
  }

  // Text field
  if (field.field_type === 'text') {
    return (
      <Box sx={{ py: 2 }}>
        <TextField
          fullWidth
          label={field.label || 'Enter text'}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={disabled}
          multiline={field.multiline}
          rows={field.multiline ? 3 : 1}
          sx={{ mb: 2 }}
        />
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={disabled || (field.is_required && !inputValue.trim())}
        >
          Save
        </Button>
      </Box>
    );
  }

  // Checkbox field
  if (field.field_type === 'checkbox') {
    return (
      <Box sx={{ py: 2 }}>
        <FormControlLabel
          control={
            <Checkbox
              checked={checkboxValue}
              onChange={(e) => setCheckboxValue(e.target.checked)}
              disabled={disabled}
            />
          }
          label={field.label || 'Check to agree'}
        />
        <Box sx={{ mt: 2 }}>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={disabled}
          >
            Confirm
          </Button>
        </Box>
      </Box>
    );
  }

  // Dropdown field
  if (field.field_type === 'dropdown') {
    const options = field.options || [];

    return (
      <Box sx={{ py: 2 }}>
        <FormControl fullWidth sx={{ mb: 2 }}>
          <InputLabel>{field.label || 'Select option'}</InputLabel>
          <Select
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            label={field.label || 'Select option'}
            disabled={disabled}
          >
            {options.map((opt, idx) => (
              <MenuItem key={idx} value={opt}>
                {opt}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={disabled || (field.is_required && !inputValue)}
        >
          Save
        </Button>
      </Box>
    );
  }

  return null;
};

/**
 * Main Signing Session Page
 */
const SigningSession = () => {
  const { token } = useParams();
  const navigate = useNavigate();

  // Session state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [session, setSession] = useState(null);
  const [documentUrl, setDocumentUrl] = useState(null);

  // Field state
  const [currentFieldIndex, setCurrentFieldIndex] = useState(0);
  const [fieldValues, setFieldValues] = useState({});
  const [submittingField, setSubmittingField] = useState(false);

  // Signature state
  const [adoptedSignature, setAdoptedSignature] = useState(null);
  const [showSignatureModal, setShowSignatureModal] = useState(false);
  const [adoptingSignature, setAdoptingSignature] = useState(false);

  // Completion state
  const [completing, setCompleting] = useState(false);
  const [completed, setCompleted] = useState(false);

  // PDF viewer state
  const [zoom, setZoom] = useState(100);
  const viewerRef = useRef(null);
  const [viewerRect, setViewerRect] = useState(null);

  // Load session data
  useEffect(() => {
    const loadSession = async () => {
      try {
        setLoading(true);
        setError(null);

        // Validate token and get session data
        const sessionData = await esignApi.validateSigningToken(token);
        setSession(sessionData);

        // Check if signer already adopted signature
        if (sessionData.signer?.adopted_signature_text) {
          setAdoptedSignature({
            text: sessionData.signer.adopted_signature_text,
            font: sessionData.signer.adopted_signature_font,
          });
        }

        // Pre-populate field values
        const values = {};
        if (sessionData.field_values) {
          sessionData.field_values.forEach((fv) => {
            values[fv.field_id] = fv.text_value || fv.boolean_value;
          });
        }
        setFieldValues(values);

        // Get document URL
        const docData = await esignApi.getSigningDocument(token);
        setDocumentUrl(docData.url);
      } catch (err) {
        console.error('Failed to load signing session:', err);
        setError(err.message || 'Failed to load signing session');
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      loadSession();
    }
  }, [token]);

  // Update viewer rect on resize
  useEffect(() => {
    const updateRect = () => {
      if (viewerRef.current) {
        setViewerRect(viewerRef.current.getBoundingClientRect());
      }
    };

    updateRect();
    window.addEventListener('resize', updateRect);
    return () => window.removeEventListener('resize', updateRect);
  }, []);

  // Get signer's fields sorted by page and position
  const signerFields = session?.fields
    ?.filter((f) => f.signer_id === session.signer?.id)
    .sort((a, b) => {
      if (a.page_number !== b.page_number) return a.page_number - b.page_number;
      return a.y_position_points - b.y_position_points;
    }) || [];

  const currentField = signerFields[currentFieldIndex];
  const completedCount = signerFields.filter((f) => fieldValues[f.id] !== undefined).length;
  const requiredFields = signerFields.filter((f) => f.is_required);
  const completedRequired = requiredFields.filter((f) => fieldValues[f.id] !== undefined).length;
  const canComplete = completedRequired === requiredFields.length;

  // Handle field submission
  const handleFieldSubmit = async (fieldId, value) => {
    try {
      setSubmittingField(true);
      await esignApi.submitFieldValue(token, fieldId, value);
      setFieldValues((prev) => ({ ...prev, [fieldId]: value }));

      // Auto-advance to next incomplete field
      const nextIncomplete = signerFields.findIndex(
        (f, idx) => idx > currentFieldIndex && fieldValues[f.id] === undefined
      );
      if (nextIncomplete !== -1) {
        setCurrentFieldIndex(nextIncomplete);
      }
    } catch (err) {
      console.error('Failed to submit field:', err);
      setError(err.message || 'Failed to save field value');
    } finally {
      setSubmittingField(false);
    }
  };

  // Handle signature adoption
  const handleAdoptSignature = async (text, fontId) => {
    try {
      setAdoptingSignature(true);
      await esignApi.adoptSignature(token, text, fontId);
      setAdoptedSignature({ text, font: fontId });
      setShowSignatureModal(false);
    } catch (err) {
      console.error('Failed to adopt signature:', err);
      setError(err.message || 'Failed to adopt signature');
    } finally {
      setAdoptingSignature(false);
    }
  };

  // Handle signing completion
  const handleComplete = async () => {
    try {
      setCompleting(true);
      await esignApi.completeSigning(token);
      setCompleted(true);
    } catch (err) {
      console.error('Failed to complete signing:', err);
      setError(err.message || 'Failed to complete signing');
    } finally {
      setCompleting(false);
    }
  };

  // Navigate fields
  const goToPrevField = () => {
    if (currentFieldIndex > 0) {
      setCurrentFieldIndex(currentFieldIndex - 1);
    }
  };

  const goToNextField = () => {
    if (currentFieldIndex < signerFields.length - 1) {
      setCurrentFieldIndex(currentFieldIndex + 1);
    }
  };

  // Loading state
  if (loading) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <CircularProgress size={48} />
        <Typography color="text.secondary">Loading document...</Typography>
      </Box>
    );
  }

  // Error state
  if (error && !session) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 3,
        }}
      >
        <Paper sx={{ p: 4, maxWidth: 500, textAlign: 'center' }}>
          <Typography variant="h5" color="error" gutterBottom>
            Unable to Load Document
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            {error}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The signing link may have expired or is invalid.
            Please contact the sender for a new link.
          </Typography>
        </Paper>
      </Box>
    );
  }

  // Completion state
  if (completed) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 3,
          backgroundColor: '#f5f5f5',
        }}
      >
        <Paper sx={{ p: 5, maxWidth: 500, textAlign: 'center' }}>
          <CheckCircleIcon sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
          <Typography variant="h4" gutterBottom>
            Signing Complete!
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            Thank you for signing "{session?.envelope?.name}".
            You will receive a copy of the signed document via email.
          </Typography>
          <Button
            variant="outlined"
            onClick={() => window.close()}
          >
            Close Window
          </Button>
        </Paper>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Paper
        elevation={1}
        sx={{
          p: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderRadius: 0,
        }}
      >
        <Box>
          <Typography variant="h6">{session?.envelope?.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            Signing as: {session?.signer?.name} ({session?.signer?.email})
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Chip
            label={`${completedCount}/${signerFields.length} fields completed`}
            color={canComplete ? 'success' : 'default'}
            size="small"
          />
          <Button
            variant="contained"
            color="success"
            startIcon={completing ? <CircularProgress size={16} color="inherit" /> : <DoneIcon />}
            onClick={handleComplete}
            disabled={!canComplete || completing}
          >
            {completing ? 'Completing...' : 'Complete Signing'}
          </Button>
        </Box>
      </Paper>

      {/* Progress bar */}
      <LinearProgress
        variant="determinate"
        value={(completedCount / signerFields.length) * 100}
        sx={{ height: 4 }}
      />

      {/* Error alert */}
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ m: 1 }}>
          {error}
        </Alert>
      )}

      {/* Main content */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* PDF Viewer */}
        <Box
          sx={{
            flex: 2,
            backgroundColor: '#525659',
            overflow: 'auto',
            position: 'relative',
          }}
        >
          {/* Zoom controls */}
          <Box
            sx={{
              position: 'absolute',
              top: 16,
              left: 16,
              zIndex: 10,
              display: 'flex',
              gap: 1,
              backgroundColor: 'rgba(255,255,255,0.9)',
              borderRadius: 1,
              p: 0.5,
            }}
          >
            <IconButton size="small" onClick={() => setZoom(Math.max(50, zoom - 25))}>
              <ZoomOutIcon />
            </IconButton>
            <Typography sx={{ minWidth: 50, textAlign: 'center', lineHeight: '30px' }}>
              {zoom}%
            </Typography>
            <IconButton size="small" onClick={() => setZoom(Math.min(200, zoom + 25))}>
              <ZoomInIcon />
            </IconButton>
          </Box>

          {/* PDF iframe */}
          <Box
            ref={viewerRef}
            sx={{
              width: `${zoom}%`,
              minHeight: '100%',
              margin: '0 auto',
              position: 'relative',
            }}
          >
            {documentUrl && (
              <iframe
                src={documentUrl}
                title="Document"
                style={{
                  width: '100%',
                  height: '800px',
                  border: 'none',
                  backgroundColor: '#fff',
                }}
              />
            )}

            {/* Field overlays - simplified for signing session */}
            {signerFields.map((field, idx) => {
              const isCompleted = fieldValues[field.id] !== undefined;
              const isCurrent = idx === currentFieldIndex;
              const fieldConfig = FIELD_TYPES[field.field_type] || FIELD_TYPES.text;

              return (
                <Box
                  key={field.id}
                  onClick={() => setCurrentFieldIndex(idx)}
                  sx={{
                    position: 'absolute',
                    left: (field.x_position_points / 612) * 100 + '%',
                    top: ((792 - field.y_position_points) / 792) * 100 + '%',
                    width: (field.width_points / 612) * 100 + '%',
                    height: (field.height_points / 792) * 100 + '%',
                    backgroundColor: isCompleted
                      ? 'rgba(76, 175, 80, 0.3)'
                      : isCurrent
                      ? 'rgba(26, 115, 232, 0.4)'
                      : 'rgba(26, 115, 232, 0.2)',
                    border: isCurrent ? '2px solid #1a73e8' : '1px dashed rgba(0,0,0,0.3)',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.2s',
                    '&:hover': {
                      backgroundColor: isCompleted
                        ? 'rgba(76, 175, 80, 0.4)'
                        : 'rgba(26, 115, 232, 0.4)',
                    },
                  }}
                >
                  {isCompleted ? (
                    <CheckCircleIcon sx={{ color: 'success.main', fontSize: 20 }} />
                  ) : (
                    <Typography
                      variant="caption"
                      sx={{
                        color: '#1a73e8',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        fontSize: '10px',
                      }}
                    >
                      {fieldConfig.label}
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
        </Box>

        {/* Right panel - Field input */}
        <Paper
          elevation={2}
          sx={{
            width: 400,
            display: 'flex',
            flexDirection: 'column',
            borderRadius: 0,
          }}
        >
          {/* Field navigation */}
          <Box
            sx={{
              p: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #e0e0e0',
            }}
          >
            <IconButton onClick={goToPrevField} disabled={currentFieldIndex === 0}>
              <PrevIcon />
            </IconButton>
            <Typography variant="body2" color="text.secondary">
              Field {currentFieldIndex + 1} of {signerFields.length}
            </Typography>
            <IconButton
              onClick={goToNextField}
              disabled={currentFieldIndex === signerFields.length - 1}
            >
              <NextIcon />
            </IconButton>
          </Box>

          {/* Current field details */}
          {currentField && (
            <Box sx={{ p: 3, flex: 1, overflow: 'auto' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                {fieldValues[currentField.id] !== undefined ? (
                  <CheckCircleIcon sx={{ color: 'success.main' }} />
                ) : (
                  <UncheckedIcon sx={{ color: 'text.disabled' }} />
                )}
                <Typography variant="h6">
                  {FIELD_TYPES[currentField.field_type]?.label || currentField.field_type}
                </Typography>
                {currentField.is_required && (
                  <Chip label="Required" size="small" color="error" variant="outlined" />
                )}
              </Box>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Page {currentField.page_number}
                {currentField.label && ` • ${currentField.label}`}
              </Typography>

              <Divider sx={{ my: 2 }} />

              <FieldInput
                field={currentField}
                value={fieldValues[currentField.id]}
                adoptedSignature={adoptedSignature}
                onSubmit={handleFieldSubmit}
                onRequestSignature={() => setShowSignatureModal(true)}
                disabled={submittingField}
              />
            </Box>
          )}

          {/* Field list */}
          <Box
            sx={{
              borderTop: '1px solid #e0e0e0',
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            <Typography
              variant="subtitle2"
              sx={{ p: 2, pb: 1, color: 'text.secondary' }}
            >
              All Fields
            </Typography>
            {signerFields.map((field, idx) => {
              const isCompleted = fieldValues[field.id] !== undefined;
              const isCurrent = idx === currentFieldIndex;

              return (
                <Box
                  key={field.id}
                  onClick={() => setCurrentFieldIndex(idx)}
                  sx={{
                    px: 2,
                    py: 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    cursor: 'pointer',
                    backgroundColor: isCurrent ? '#e8f0fe' : 'transparent',
                    '&:hover': { backgroundColor: isCurrent ? '#e8f0fe' : '#f5f5f5' },
                  }}
                >
                  {isCompleted ? (
                    <CheckCircleIcon sx={{ color: 'success.main', fontSize: 18 }} />
                  ) : (
                    <UncheckedIcon sx={{ color: 'text.disabled', fontSize: 18 }} />
                  )}
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    {FIELD_TYPES[field.field_type]?.label || field.field_type}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Page {field.page_number}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Paper>
      </Box>

      {/* Signature Adoption Modal */}
      <SignatureAdoptionModal
        open={showSignatureModal}
        onClose={() => setShowSignatureModal(false)}
        onAdopt={handleAdoptSignature}
        signerName={session?.signer?.name || ''}
        loading={adoptingSignature}
      />
    </Box>
  );
};

export default SigningSession;
