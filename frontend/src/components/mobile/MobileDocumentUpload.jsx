/**
 * MobileDocumentUpload Component
 *
 * Mobile-optimized document capture and upload flow for loan officers in the field.
 * Supports camera capture, photo library, file browsing, multi-page documents,
 * image rotation, crop, and direct upload to Smart Docs API.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { camera, haptics, isNative } from '../../services/nativeServices';
import { uploadDocument } from '../../services/smartDocsApi';
import './MobileDocumentUpload.css';

// Document type categories matching DOCUMENT_CATEGORIES from backend
const DOC_CATEGORIES = {
  income: {
    label: 'Income',
    icon: 'dollar',
    types: [
      { value: 'paystubs', label: 'Paystubs' },
      { value: 'w2', label: 'W-2' },
      { value: 'tax_returns', label: 'Tax Returns' },
      { value: '1099', label: '1099' },
      { value: 'profit_loss', label: 'P&L Statement' },
    ],
  },
  assets: {
    label: 'Assets',
    icon: 'bank',
    types: [
      { value: 'bank_statements', label: 'Bank Statements' },
      { value: 'investment_statements', label: 'Investment Statements' },
      { value: 'gift_letter', label: 'Gift Letter' },
    ],
  },
  property: {
    label: 'Property',
    icon: 'home',
    types: [
      { value: 'purchase_contract', label: 'Purchase Contract' },
      { value: 'appraisal', label: 'Appraisal' },
      { value: 'title', label: 'Title' },
      { value: 'insurance', label: 'Insurance' },
    ],
  },
  identity: {
    label: 'Identity',
    icon: 'id',
    types: [
      { value: 'drivers_license', label: "Driver's License" },
      { value: 'passport', label: 'Passport' },
    ],
  },
  other: {
    label: 'Other',
    icon: 'file',
    types: [
      { value: 'other', label: 'Other Document' },
    ],
  },
};

const JPEG_QUALITY = 80;
const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

/**
 * Convert a base64 data URL to a File object
 */
function dataUrlToFile(dataUrl, filename) {
  const [header, data] = dataUrl.split(',');
  const mime = header.match(/:(.*?);/)[1];
  const bytes = atob(data);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) {
    arr[i] = bytes.charCodeAt(i);
  }
  return new File([arr], filename, { type: mime });
}

/**
 * Estimate base64 data size in bytes
 */
function estimateBase64Size(base64String) {
  if (!base64String) return 0;
  const padding = (base64String.match(/=/g) || []).length;
  return Math.floor((base64String.length * 3) / 4) - padding;
}

/**
 * Rotate an image by degrees and return new dataUrl
 */
function rotateImage(dataUrl, degrees) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const rads = (degrees * Math.PI) / 180;
      const isOrthogonal = degrees % 180 !== 0;

      canvas.width = isOrthogonal ? img.height : img.width;
      canvas.height = isOrthogonal ? img.width : img.height;

      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate(rads);
      ctx.drawImage(img, -img.width / 2, -img.height / 2);

      resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY / 100));
    };
    img.src = dataUrl;
  });
}

/**
 * Crop an image to the given rect {x, y, width, height} (in percentages 0-1)
 */
function cropImage(dataUrl, cropRect) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      const sx = Math.round(cropRect.x * img.width);
      const sy = Math.round(cropRect.y * img.height);
      const sw = Math.round(cropRect.width * img.width);
      const sh = Math.round(cropRect.height * img.height);

      canvas.width = sw;
      canvas.height = sh;
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);

      resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY / 100));
    };
    img.src = dataUrl;
  });
}


// ============================================================================
// Sub-components
// ============================================================================

function SourceSheet({ onSelect, onClose }) {
  useEffect(() => {
    // Animate in
    const timer = setTimeout(() => {
      const el = document.querySelector('.mdu-source-sheet__panel');
      if (el) el.classList.add('mdu-source-sheet__panel--visible');
    }, 10);
    return () => clearTimeout(timer);
  }, []);

  const handleSelect = (source) => {
    haptics.light();
    onSelect(source);
  };

  return (
    <div className="mdu-source-sheet" onClick={onClose} role="dialog" aria-label="Choose document source">
      <div className="mdu-source-sheet__panel" onClick={(e) => e.stopPropagation()}>
        <div className="mdu-source-sheet__handle" />
        <h3 className="mdu-source-sheet__title">Add Document</h3>

        <button className="mdu-source-sheet__option" onClick={() => handleSelect('camera')}>
          <span className="mdu-source-sheet__icon mdu-source-sheet__icon--camera">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </span>
          <div className="mdu-source-sheet__option-text">
            <span className="mdu-source-sheet__option-label">Take Photo</span>
            <span className="mdu-source-sheet__option-desc">Use camera to capture document</span>
          </div>
        </button>

        <button className="mdu-source-sheet__option" onClick={() => handleSelect('gallery')}>
          <span className="mdu-source-sheet__icon mdu-source-sheet__icon--gallery">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          </span>
          <div className="mdu-source-sheet__option-text">
            <span className="mdu-source-sheet__option-label">Choose from Library</span>
            <span className="mdu-source-sheet__option-desc">Select from your photo library</span>
          </div>
        </button>

        <button className="mdu-source-sheet__option" onClick={() => handleSelect('file')}>
          <span className="mdu-source-sheet__icon mdu-source-sheet__icon--file">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </span>
          <div className="mdu-source-sheet__option-text">
            <span className="mdu-source-sheet__option-label">Browse Files</span>
            <span className="mdu-source-sheet__option-desc">Upload PDF or image from files</span>
          </div>
        </button>

        <button className="mdu-source-sheet__cancel" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function PhotoReview({ page, onAccept, onRetake, onRotate, onCropToggle, isCropping, cropRect, onCropChange }) {
  const imageRef = useRef(null);
  const cropStartRef = useRef(null);

  const handleCropStart = (e) => {
    if (!isCropping) return;
    const rect = imageRef.current.getBoundingClientRect();
    const touch = e.touches ? e.touches[0] : e;
    cropStartRef.current = {
      x: (touch.clientX - rect.left) / rect.width,
      y: (touch.clientY - rect.top) / rect.height,
    };
  };

  const handleCropMove = (e) => {
    if (!isCropping || !cropStartRef.current) return;
    e.preventDefault();
    const rect = imageRef.current.getBoundingClientRect();
    const touch = e.touches ? e.touches[0] : e;
    const endX = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
    const endY = Math.max(0, Math.min(1, (touch.clientY - rect.top) / rect.height));
    const startX = cropStartRef.current.x;
    const startY = cropStartRef.current.y;

    onCropChange({
      x: Math.min(startX, endX),
      y: Math.min(startY, endY),
      width: Math.abs(endX - startX),
      height: Math.abs(endY - startY),
    });
  };

  const handleCropEnd = () => {
    cropStartRef.current = null;
  };

  return (
    <div className="mdu-review">
      <div className="mdu-review__header">
        <span className="mdu-review__page-label">Page {page.pageNumber}</span>
      </div>
      <div
        className="mdu-review__image-container"
        onTouchStart={handleCropStart}
        onTouchMove={handleCropMove}
        onTouchEnd={handleCropEnd}
        onMouseDown={handleCropStart}
        onMouseMove={handleCropMove}
        onMouseUp={handleCropEnd}
      >
        <img
          ref={imageRef}
          src={page.dataUrl}
          alt={`Captured page ${page.pageNumber}`}
          className="mdu-review__image"
        />
        {isCropping && cropRect && cropRect.width > 0 && (
          <div
            className="mdu-review__crop-overlay"
            style={{
              left: `${cropRect.x * 100}%`,
              top: `${cropRect.y * 100}%`,
              width: `${cropRect.width * 100}%`,
              height: `${cropRect.height * 100}%`,
            }}
          />
        )}
      </div>
      <div className="mdu-review__actions">
        <button className="mdu-review__btn mdu-review__btn--secondary" onClick={onRetake}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="1 4 1 10 7 10" />
            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
          </svg>
          Retake
        </button>
        <button className="mdu-review__btn mdu-review__btn--secondary" onClick={onRotate}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          Rotate
        </button>
        <button
          className={`mdu-review__btn mdu-review__btn--secondary ${isCropping ? 'mdu-review__btn--active' : ''}`}
          onClick={onCropToggle}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6.13 1L6 16a2 2 0 0 0 2 2h15" />
            <path d="M1 6.13L16 6a2 2 0 0 1 2 2v15" />
          </svg>
          Crop
        </button>
        <button className="mdu-review__btn mdu-review__btn--primary" onClick={onAccept}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          Accept
        </button>
      </div>
    </div>
  );
}

function DocTypePicker({ selectedType, onSelect }) {
  const [expandedCategory, setExpandedCategory] = useState(null);
  const [customLabel, setCustomLabel] = useState('');

  const handleCategoryTap = (catKey) => {
    haptics.selection();
    setExpandedCategory(expandedCategory === catKey ? null : catKey);
  };

  const handleTypeSelect = (typeValue) => {
    haptics.light();
    onSelect(typeValue === 'other' && customLabel.trim() ? customLabel.trim() : typeValue);
  };

  return (
    <div className="mdu-doctype">
      <h3 className="mdu-doctype__title">Document Type</h3>
      <p className="mdu-doctype__subtitle">What kind of document is this?</p>
      <div className="mdu-doctype__categories">
        {Object.entries(DOC_CATEGORIES).map(([catKey, cat]) => (
          <div key={catKey} className="mdu-doctype__category">
            <button
              className={`mdu-doctype__category-btn ${expandedCategory === catKey ? 'mdu-doctype__category-btn--expanded' : ''}`}
              onClick={() => handleCategoryTap(catKey)}
            >
              <CategoryIcon icon={cat.icon} />
              <span>{cat.label}</span>
              <svg
                className="mdu-doctype__chevron"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {expandedCategory === catKey && (
              <div className="mdu-doctype__types">
                {cat.types.map((type) => (
                  <button
                    key={type.value}
                    className={`mdu-doctype__type-btn ${selectedType === type.value ? 'mdu-doctype__type-btn--selected' : ''}`}
                    onClick={() => handleTypeSelect(type.value)}
                  >
                    <span>{type.label}</span>
                    {selectedType === type.value && (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>
                ))}
                {catKey === 'other' && expandedCategory === 'other' && (
                  <div className="mdu-doctype__custom">
                    <input
                      type="text"
                      className="mdu-doctype__custom-input"
                      placeholder="Enter document type..."
                      value={customLabel}
                      onChange={(e) => setCustomLabel(e.target.value)}
                      maxLength={100}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function CategoryIcon({ icon }) {
  const strokeColor = 'currentColor';
  switch (icon) {
    case 'dollar':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={strokeColor} strokeWidth="2">
          <line x1="12" y1="1" x2="12" y2="23" />
          <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
        </svg>
      );
    case 'bank':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={strokeColor} strokeWidth="2">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
        </svg>
      );
    case 'home':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={strokeColor} strokeWidth="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      );
    case 'id':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={strokeColor} strokeWidth="2">
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <line x1="2" y1="10" x2="22" y2="10" />
        </svg>
      );
    case 'file':
    default:
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={strokeColor} strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      );
  }
}

function LoanSelector({ loans, selectedLoanId, onSelect }) {
  return (
    <div className="mdu-loan-select">
      <h3 className="mdu-loan-select__title">Associate with Loan</h3>
      <div className="mdu-loan-select__list">
        {loans.map((loan) => (
          <button
            key={loan.id}
            className={`mdu-loan-select__item ${selectedLoanId === loan.id ? 'mdu-loan-select__item--selected' : ''}`}
            onClick={() => { haptics.selection(); onSelect(loan.id); }}
          >
            <div className="mdu-loan-select__item-info">
              <span className="mdu-loan-select__item-name">{loan.borrower_name || loan.loan_number}</span>
              <span className="mdu-loan-select__item-detail">
                {loan.loan_number} {loan.property_address ? `- ${loan.property_address}` : ''}
              </span>
            </div>
            {selectedLoanId === loan.id && (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function UploadProgress({ progress, onCancel }) {
  return (
    <div className="mdu-progress">
      <div className="mdu-progress__icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" strokeWidth="1.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
      </div>
      <p className="mdu-progress__label">Uploading document...</p>
      <div className="mdu-progress__bar-container">
        <div className="mdu-progress__bar" style={{ width: `${progress}%` }} />
      </div>
      <span className="mdu-progress__percent">{Math.round(progress)}%</span>
      <button className="mdu-progress__cancel" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}

function SuccessState({ pageCount, docType, onUploadAnother, onDone }) {
  useEffect(() => {
    haptics.success();
  }, []);

  return (
    <div className="mdu-success">
      <div className="mdu-success__icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      </div>
      <h3 className="mdu-success__title">Document Uploaded</h3>
      <p className="mdu-success__detail">
        {pageCount > 1 ? `${pageCount} pages` : '1 page'} uploaded as {docType || 'document'}
      </p>
      <div className="mdu-success__actions">
        <button className="mdu-success__btn mdu-success__btn--primary" onClick={onUploadAnother}>
          Upload Another
        </button>
        <button className="mdu-success__btn mdu-success__btn--secondary" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}

function PageThumbnails({ pages, currentIndex, onSelect, onRemove }) {
  return (
    <div className="mdu-thumbnails">
      <div className="mdu-thumbnails__scroll">
        {pages.map((page, idx) => (
          <div
            key={idx}
            className={`mdu-thumbnails__item ${idx === currentIndex ? 'mdu-thumbnails__item--active' : ''}`}
            onClick={() => onSelect(idx)}
          >
            <img src={page.dataUrl} alt={`Page ${idx + 1}`} className="mdu-thumbnails__img" />
            <span className="mdu-thumbnails__number">{idx + 1}</span>
            {pages.length > 1 && (
              <button
                className="mdu-thumbnails__remove"
                onClick={(e) => { e.stopPropagation(); onRemove(idx); }}
                aria-label={`Remove page ${idx + 1}`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


// ============================================================================
// Main component
// ============================================================================

export default function MobileDocumentUpload({
  loanId: initialLoanId = null,
  borrowerId: initialBorrowerId = null,
  loans = [],
  onComplete,
  onClose,
}) {
  // Flow steps: source -> review -> doctype -> loan -> uploading -> success
  const [step, setStep] = useState('source');
  const [pages, setPages] = useState([]);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [rotation, setRotation] = useState(0);
  const [isCropping, setIsCropping] = useState(false);
  const [cropRect, setCropRect] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const [selectedDocType, setSelectedDocType] = useState(null);
  const [selectedLoanId, setSelectedLoanId] = useState(initialLoanId);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [sizeWarning, setSizeWarning] = useState(null);

  const fileInputRef = useRef(null);
  const abortControllerRef = useRef(null);

  const needsLoanSelect = !initialLoanId && loans.length > 0;

  // Reset flow to initial state
  const resetFlow = useCallback(() => {
    setStep('source');
    setPages([]);
    setCurrentPageIndex(0);
    setRotation(0);
    setIsCropping(false);
    setCropRect({ x: 0, y: 0, width: 0, height: 0 });
    setSelectedDocType(null);
    setSizeWarning(null);
    setError(null);
    setUploadProgress(0);
  }, []);

  // Capture from camera
  const captureFromCamera = useCallback(async () => {
    try {
      setError(null);
      const result = await camera.takePhoto({ quality: JPEG_QUALITY });
      if (!result) return; // user cancelled

      const sizeBytes = estimateBase64Size(result.base64);
      if (sizeBytes > MAX_FILE_SIZE_BYTES) {
        setSizeWarning(`Photo is ${(sizeBytes / (1024 * 1024)).toFixed(1)}MB. Files over ${MAX_FILE_SIZE_MB}MB may fail to upload.`);
      }

      const newPage = {
        dataUrl: result.dataUrl,
        format: result.format || 'jpeg',
        pageNumber: pages.length + 1,
        source: 'camera',
      };
      setPages((prev) => [...prev, newPage]);
      setCurrentPageIndex(pages.length);
      setStep('review');
    } catch (err) {
      if (err.message?.includes('User cancelled') || err.message?.includes('cancelled')) {
        return;
      }
      setError('Failed to capture photo. Please try again.');
    }
  }, [pages.length]);

  // Pick from gallery
  const pickFromGallery = useCallback(async () => {
    try {
      setError(null);
      const result = await camera.pickFromGallery({ quality: JPEG_QUALITY });
      if (!result) return;

      const sizeBytes = estimateBase64Size(result.base64);
      if (sizeBytes > MAX_FILE_SIZE_BYTES) {
        setSizeWarning(`Photo is ${(sizeBytes / (1024 * 1024)).toFixed(1)}MB. Files over ${MAX_FILE_SIZE_MB}MB may fail to upload.`);
      }

      const newPage = {
        dataUrl: result.dataUrl,
        format: result.format || 'jpeg',
        pageNumber: pages.length + 1,
        source: 'gallery',
      };
      setPages((prev) => [...prev, newPage]);
      setCurrentPageIndex(pages.length);
      setStep('review');
    } catch (err) {
      if (err.message?.includes('User cancelled') || err.message?.includes('cancelled')) {
        return;
      }
      setError('Failed to select photo. Please try again.');
    }
  }, [pages.length]);

  // Browse files (fallback for non-native or PDFs)
  const handleFileSelect = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setSizeWarning(`File is ${(file.size / (1024 * 1024)).toFixed(1)}MB. Files over ${MAX_FILE_SIZE_MB}MB may fail to upload.`);
    }

    // If it's a PDF, skip photo review, go straight to doctype
    if (file.type === 'application/pdf') {
      const newPage = {
        file,
        dataUrl: null,
        format: 'pdf',
        pageNumber: 1,
        source: 'file',
        fileName: file.name,
      };
      setPages([newPage]);
      setCurrentPageIndex(0);
      setStep('doctype');
      return;
    }

    // For images, read and show review
    const reader = new FileReader();
    reader.onload = () => {
      const newPage = {
        dataUrl: reader.result,
        format: file.type.split('/')[1] || 'jpeg',
        pageNumber: pages.length + 1,
        source: 'file',
        fileName: file.name,
      };
      setPages((prev) => [...prev, newPage]);
      setCurrentPageIndex(pages.length);
      setStep('review');
    };
    reader.readAsDataURL(file);

    // Reset input so same file can be re-selected
    e.target.value = '';
  }, [pages.length]);

  // Source selection handler
  const handleSourceSelect = useCallback((source) => {
    if (source === 'camera') {
      captureFromCamera();
    } else if (source === 'gallery') {
      pickFromGallery();
    } else if (source === 'file') {
      fileInputRef.current?.click();
    }
  }, [captureFromCamera, pickFromGallery]);

  // Rotate current page
  const handleRotate = useCallback(async () => {
    const page = pages[currentPageIndex];
    if (!page?.dataUrl) return;

    haptics.light();
    const newRotation = (rotation + 90) % 360;
    setRotation(newRotation);

    const rotated = await rotateImage(page.dataUrl, 90);
    setPages((prev) => {
      const updated = [...prev];
      updated[currentPageIndex] = { ...updated[currentPageIndex], dataUrl: rotated };
      return updated;
    });
  }, [currentPageIndex, pages, rotation]);

  // Apply crop to current page
  const handleCropToggle = useCallback(async () => {
    if (isCropping && cropRect.width > 0.05 && cropRect.height > 0.05) {
      // Apply crop
      const page = pages[currentPageIndex];
      if (page?.dataUrl) {
        haptics.medium();
        const cropped = await cropImage(page.dataUrl, cropRect);
        setPages((prev) => {
          const updated = [...prev];
          updated[currentPageIndex] = { ...updated[currentPageIndex], dataUrl: cropped };
          return updated;
        });
      }
      setCropRect({ x: 0, y: 0, width: 0, height: 0 });
    }
    setIsCropping(!isCropping);
  }, [isCropping, cropRect, currentPageIndex, pages]);

  // Retake current page
  const handleRetake = useCallback(() => {
    haptics.light();
    const page = pages[currentPageIndex];
    // Remove current page and go back to source
    setPages((prev) => prev.filter((_, i) => i !== currentPageIndex));
    if (pages.length <= 1) {
      setStep('source');
      setCurrentPageIndex(0);
    } else {
      setCurrentPageIndex(Math.max(0, currentPageIndex - 1));
    }
    // Re-open the same source
    if (page?.source === 'camera') {
      captureFromCamera();
    } else if (page?.source === 'gallery') {
      pickFromGallery();
    } else {
      setStep('source');
    }
  }, [currentPageIndex, pages, captureFromCamera, pickFromGallery]);

  // Accept current page
  const handleAcceptPage = useCallback(() => {
    haptics.success();
    setRotation(0);
    setIsCropping(false);
    setCropRect({ x: 0, y: 0, width: 0, height: 0 });
    setStep('doctype');
  }, []);

  // Add another page
  const handleAddPage = useCallback(() => {
    setStep('source');
  }, []);

  // Remove page from multi-page set
  const handleRemovePage = useCallback((idx) => {
    haptics.light();
    setPages((prev) => {
      const updated = prev.filter((_, i) => i !== idx);
      return updated.map((p, i) => ({ ...p, pageNumber: i + 1 }));
    });
    if (currentPageIndex >= pages.length - 1) {
      setCurrentPageIndex(Math.max(0, pages.length - 2));
    }
  }, [currentPageIndex, pages.length]);

  // Handle doc type selection -> proceed to loan select or upload
  const handleDocTypeSelected = useCallback((docType) => {
    setSelectedDocType(docType);
    if (needsLoanSelect && !selectedLoanId) {
      setStep('loan');
    } else {
      handleUpload(docType, selectedLoanId || initialLoanId);
    }
  }, [needsLoanSelect, selectedLoanId, initialLoanId]);

  // Handle loan selection -> proceed to upload
  const handleLoanSelected = useCallback((loanId) => {
    setSelectedLoanId(loanId);
  }, []);

  const handleLoanConfirm = useCallback(() => {
    if (selectedLoanId && selectedDocType) {
      handleUpload(selectedDocType, selectedLoanId);
    }
  }, [selectedLoanId, selectedDocType]);

  // Upload the document
  const handleUpload = useCallback(async (docType, loanId) => {
    setStep('uploading');
    setUploadProgress(0);
    setError(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      let fileToUpload;

      // If single PDF file, upload directly
      if (pages.length === 1 && pages[0].file) {
        fileToUpload = pages[0].file;
      } else if (pages.length === 1 && pages[0].dataUrl) {
        // Single image page
        fileToUpload = dataUrlToFile(pages[0].dataUrl, `document_${Date.now()}.jpg`);
      } else {
        // Multi-page: combine images into a single file
        // For multi-page, we upload each as a canvas-rendered JPEG
        // (The backend handles multi-page association)
        // Upload first page as the main document
        fileToUpload = dataUrlToFile(pages[0].dataUrl, `document_${Date.now()}_p1.jpg`);
      }

      // Check final file size
      if (fileToUpload.size > MAX_FILE_SIZE_BYTES) {
        setSizeWarning(`File size is ${(fileToUpload.size / (1024 * 1024)).toFixed(1)}MB which exceeds ${MAX_FILE_SIZE_MB}MB. Upload may be slow or fail.`);
      }

      // Simulate progress (real progress would need XMLHttpRequest)
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + Math.random() * 15;
        });
      }, 300);

      // Upload the main document
      const result = await uploadDocument(
        fileToUpload,
        loanId,
        initialBorrowerId || 'auto',
        null,
        docType,
      );

      clearInterval(progressInterval);

      // Upload additional pages if multi-page
      if (pages.length > 1) {
        for (let i = 1; i < pages.length; i++) {
          if (pages[i].dataUrl) {
            const pageFile = dataUrlToFile(pages[i].dataUrl, `document_${Date.now()}_p${i + 1}.jpg`);
            try {
              await uploadDocument(
                pageFile,
                loanId,
                initialBorrowerId || 'auto',
                null,
                docType,
              );
            } catch (pageErr) {
              console.error(`Failed to upload page ${i + 1}:`, pageErr);
              // Continue with remaining pages
            }
          }
        }
      }

      setUploadProgress(100);
      haptics.success();

      // Brief pause to show 100%
      setTimeout(() => {
        setStep('success');
        if (onComplete) {
          onComplete({
            loanId,
            docType,
            pageCount: pages.length,
            result,
          });
        }
      }, 400);
    } catch (err) {
      if (err.name === 'AbortError') return;

      haptics.error();
      setError(err.message || 'Upload failed. Please try again.');
      setStep('doctype');
    }
  }, [pages, initialBorrowerId, onComplete]);

  // Cancel upload
  const handleCancelUpload = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setStep('doctype');
    setUploadProgress(0);
  }, []);

  // Render based on current step
  const renderStep = () => {
    switch (step) {
      case 'source':
        return (
          <SourceSheet
            onSelect={handleSourceSelect}
            onClose={onClose}
          />
        );

      case 'review':
        return (
          <>
            {pages.length > 1 && (
              <PageThumbnails
                pages={pages}
                currentIndex={currentPageIndex}
                onSelect={setCurrentPageIndex}
                onRemove={handleRemovePage}
              />
            )}
            {pages[currentPageIndex] && (
              <PhotoReview
                page={pages[currentPageIndex]}
                onAccept={handleAcceptPage}
                onRetake={handleRetake}
                onRotate={handleRotate}
                onCropToggle={handleCropToggle}
                isCropping={isCropping}
                cropRect={cropRect}
                onCropChange={setCropRect}
              />
            )}
          </>
        );

      case 'doctype':
        return (
          <div className="mdu-step-container">
            {pages.length > 0 && pages[0].dataUrl && (
              <div className="mdu-step-preview">
                <img src={pages[0].dataUrl} alt="Document preview" className="mdu-step-preview__img" />
                <span className="mdu-step-preview__badge">
                  {pages.length} {pages.length === 1 ? 'page' : 'pages'}
                </span>
              </div>
            )}
            {pages.length > 0 && !pages[0].dataUrl && pages[0].fileName && (
              <div className="mdu-step-preview mdu-step-preview--file">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.5">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="mdu-step-preview__filename">{pages[0].fileName}</span>
              </div>
            )}

            <DocTypePicker
              selectedType={selectedDocType}
              onSelect={handleDocTypeSelected}
            />

            <button className="mdu-add-page-btn" onClick={handleAddPage}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add Another Page
            </button>
          </div>
        );

      case 'loan':
        return (
          <div className="mdu-step-container">
            <LoanSelector
              loans={loans}
              selectedLoanId={selectedLoanId}
              onSelect={handleLoanSelected}
            />
            <button
              className="mdu-continue-btn"
              disabled={!selectedLoanId}
              onClick={handleLoanConfirm}
            >
              Continue
            </button>
          </div>
        );

      case 'uploading':
        return (
          <UploadProgress
            progress={uploadProgress}
            onCancel={handleCancelUpload}
          />
        );

      case 'success':
        return (
          <SuccessState
            pageCount={pages.length}
            docType={selectedDocType}
            onUploadAnother={resetFlow}
            onDone={onClose}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="mdu-container">
      {/* Hidden file input for browse */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png,.gif,.tiff"
        className="mdu-hidden-input"
        onChange={handleFileSelect}
      />

      {/* Header with close (not shown on source sheet or success) */}
      {step !== 'source' && step !== 'success' && (
        <div className="mdu-header">
          <button className="mdu-header__back" onClick={step === 'review' ? () => setStep('source') : step === 'loan' ? () => setStep('doctype') : onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h2 className="mdu-header__title">
            {step === 'review' && 'Review Photo'}
            {step === 'doctype' && 'Document Details'}
            {step === 'loan' && 'Select Loan'}
            {step === 'uploading' && 'Uploading'}
          </h2>
          <button className="mdu-header__close" onClick={onClose} aria-label="Close">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mdu-error-banner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <span>{error}</span>
          <button onClick={() => setError(null)} className="mdu-error-banner__dismiss" aria-label="Dismiss error">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Size warning */}
      {sizeWarning && (
        <div className="mdu-warning-banner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>{sizeWarning}</span>
          <button onClick={() => setSizeWarning(null)} className="mdu-warning-banner__dismiss" aria-label="Dismiss warning">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Step content */}
      <div className="mdu-content">
        {renderStep()}
      </div>
    </div>
  );
}
