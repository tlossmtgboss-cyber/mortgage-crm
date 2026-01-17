/**
 * Signature Adoption Modal
 *
 * Modal for adopting a typed signature during the signing session.
 * Features:
 * - Multiple cursive font options
 * - Real-time signature preview
 * - Terms acceptance checkbox
 * - One-time adoption per session
 */

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControlLabel,
  Checkbox,
  Typography,
  Box,
  Grid,
  Paper,
  Alert,
  CircularProgress,
} from '@mui/material';
import { SIGNATURE_FONTS } from '../../services/esignApi';

/**
 * Load Google Fonts for signature styles
 */
const loadSignatureFonts = () => {
  const fontFamilies = SIGNATURE_FONTS.map(f => f.name.replace(' ', '+')).join('|');
  const link = document.createElement('link');
  link.href = `https://fonts.googleapis.com/css2?family=${fontFamilies}&display=swap`;
  link.rel = 'stylesheet';

  // Check if already loaded
  const existing = document.querySelector(`link[href*="${fontFamilies}"]`);
  if (!existing) {
    document.head.appendChild(link);
  }
};

/**
 * Signature preview component showing the text in a specific font
 */
const SignaturePreview = ({ text, font, selected, onClick }) => {
  return (
    <Paper
      elevation={selected ? 4 : 1}
      onClick={onClick}
      sx={{
        p: 2,
        cursor: 'pointer',
        border: selected ? '2px solid #1a73e8' : '2px solid transparent',
        backgroundColor: selected ? '#e8f0fe' : '#fff',
        transition: 'all 0.2s ease',
        '&:hover': {
          borderColor: '#1a73e8',
          backgroundColor: '#f5f8fc',
        },
        minHeight: 80,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <Typography
        sx={{
          fontFamily: font.family,
          fontSize: '28px',
          color: '#1a1a1a',
          textAlign: 'center',
          wordBreak: 'break-word',
        }}
      >
        {text || 'Your Name'}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          color: '#666',
          mt: 1,
        }}
      >
        {font.name}
      </Typography>
    </Paper>
  );
};

/**
 * Main Signature Adoption Modal
 */
const SignatureAdoptionModal = ({
  open,
  onClose,
  onAdopt,
  signerName = '',
  loading = false,
  error = null,
}) => {
  const [signatureText, setSignatureText] = useState(signerName);
  const [selectedFont, setSelectedFont] = useState(SIGNATURE_FONTS[0]);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [localError, setLocalError] = useState(null);

  // Load fonts on mount
  useEffect(() => {
    loadSignatureFonts();
  }, []);

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setSignatureText(signerName);
      setSelectedFont(SIGNATURE_FONTS[0]);
      setAcceptedTerms(false);
      setLocalError(null);
    }
  }, [open, signerName]);

  const handleAdopt = () => {
    // Validate
    if (!signatureText.trim()) {
      setLocalError('Please enter your signature text');
      return;
    }

    if (!acceptedTerms) {
      setLocalError('Please accept the terms to continue');
      return;
    }

    setLocalError(null);
    onAdopt(signatureText.trim(), selectedFont.id);
  };

  const handleClose = () => {
    if (!loading) {
      onClose();
    }
  };

  const displayError = error || localError;

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2 },
      }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Typography variant="h5" component="span" fontWeight={600}>
          Adopt Your Signature
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Create your electronic signature by typing your name and selecting a style
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        {displayError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {displayError}
          </Alert>
        )}

        {/* Signature Text Input */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Type Your Full Legal Name
          </Typography>
          <TextField
            fullWidth
            value={signatureText}
            onChange={(e) => setSignatureText(e.target.value)}
            placeholder="Enter your full name"
            disabled={loading}
            inputProps={{
              maxLength: 100,
            }}
            sx={{
              '& .MuiOutlinedInput-root': {
                fontSize: '18px',
              },
            }}
          />
        </Box>

        {/* Font Selection */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Select Signature Style
          </Typography>
          <Grid container spacing={2}>
            {SIGNATURE_FONTS.map((font) => (
              <Grid item xs={12} sm={6} md={4} key={font.id}>
                <SignaturePreview
                  text={signatureText}
                  font={font}
                  selected={selectedFont.id === font.id}
                  onClick={() => !loading && setSelectedFont(font)}
                />
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* Preview */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Signature Preview
          </Typography>
          <Paper
            elevation={0}
            sx={{
              p: 3,
              backgroundColor: '#fafafa',
              border: '1px solid #e0e0e0',
              borderRadius: 1,
              textAlign: 'center',
            }}
          >
            <Typography
              sx={{
                fontFamily: selectedFont.family,
                fontSize: '36px',
                color: '#1a1a1a',
              }}
            >
              {signatureText || 'Your Signature'}
            </Typography>
            <Box
              sx={{
                width: '60%',
                height: '2px',
                backgroundColor: '#ccc',
                margin: '8px auto 0',
              }}
            />
          </Paper>
        </Box>

        {/* Terms Acceptance */}
        <Paper
          elevation={0}
          sx={{
            p: 2,
            backgroundColor: '#f5f8fc',
            border: '1px solid #d0e1f9',
            borderRadius: 1,
          }}
        >
          <FormControlLabel
            control={
              <Checkbox
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                disabled={loading}
                color="primary"
              />
            }
            label={
              <Typography variant="body2">
                I agree that my typed signature above represents my legal signature and
                that I intend to sign this document electronically. I understand that my
                electronic signature has the same legal effect as a handwritten signature.
              </Typography>
            }
          />
        </Paper>
      </DialogContent>

      <DialogActions sx={{ p: 2, gap: 1 }}>
        <Button
          onClick={handleClose}
          disabled={loading}
          color="inherit"
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleAdopt}
          disabled={loading || !signatureText.trim() || !acceptedTerms}
          sx={{
            minWidth: 160,
            backgroundColor: '#1a73e8',
            '&:hover': {
              backgroundColor: '#1557b0',
            },
          }}
        >
          {loading ? (
            <>
              <CircularProgress size={20} color="inherit" sx={{ mr: 1 }} />
              Adopting...
            </>
          ) : (
            'Adopt Signature'
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SignatureAdoptionModal;
