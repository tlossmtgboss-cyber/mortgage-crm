/**
 * Image Uploader Component
 *
 * Handles image uploads for carousel slide backgrounds.
 * Uses presigned URLs for direct S3 upload.
 */

import React, { useState, useRef, useCallback } from 'react';
import { useCarouselBuilder } from '../CarouselBuilderContext';
import { API_BASE_URL } from '../../../services/api';

export default function ImageUploader({ onUpload, currentImage }) {
  const { currentProject } = useCarouselBuilder();

  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  const fileInputRef = useRef(null);

  const handleFileSelect = useCallback(async (file) => {
    if (!file || !currentProject?.id) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      setError('Please upload a JPEG, PNG, GIF, or WebP image.');
      return;
    }

    // Validate file size (max 10MB)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('Image must be less than 10MB.');
      return;
    }

    setError(null);
    setUploading(true);
    setProgress(0);

    try {
      const token = localStorage.getItem('token');

      // Step 1: Get presigned upload URL
      setProgress(10);
      const urlResponse = await fetch(`${API_BASE_URL}/api/v1/carousels/${currentProject.id}/images/upload-url`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          file_name: file.name,
          content_type: file.type,
          file_size: file.size,
        }),
      });

      if (!urlResponse.ok) {
        const errorData = await urlResponse.json();
        throw new Error(errorData.detail || 'Failed to get upload URL');
      }

      const { upload_url, storage_key, headers } = await urlResponse.json();

      // Step 2: Upload to S3
      setProgress(30);
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: {
          'Content-Type': file.type,
          ...headers,
        },
        body: file,
      });

      if (!uploadResponse.ok) {
        throw new Error('Failed to upload image to storage');
      }

      // Step 3: Confirm upload and get public URL
      setProgress(70);
      const confirmResponse = await fetch(
        `/api/v1/carousels/${currentProject.id}/images/confirm?storage_key=${encodeURIComponent(storage_key)}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!confirmResponse.ok) {
        throw new Error('Failed to confirm upload');
      }

      const { url } = await confirmResponse.json();

      setProgress(100);

      // Notify parent component
      if (onUpload) {
        onUpload(url);
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }, [currentProject, onUpload]);

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  }, [handleFileSelect]);

  const handleInputChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleRemoveImage = () => {
    if (onUpload) {
      onUpload(null);
    }
  };

  return (
    <div className="carousel-image-uploader">
      {currentImage ? (
        <div className="carousel-image-preview">
          <img src={currentImage} alt="Background" />
          <div className="carousel-image-actions">
            <button
              type="button"
              className="btn-icon"
              onClick={() => fileInputRef.current?.click()}
              title="Replace image"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
            <button
              type="button"
              className="btn-icon btn-danger"
              onClick={handleRemoveImage}
              title="Remove image"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`carousel-image-dropzone ${dragActive ? 'drag-active' : ''} ${uploading ? 'uploading' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
        >
          {uploading ? (
            <div className="carousel-upload-progress">
              <div className="carousel-progress-bar">
                <div
                  className="carousel-progress-fill"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p>Uploading... {progress}%</p>
            </div>
          ) : (
            <>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <p>Drop image here or click to upload</p>
              <span>JPEG, PNG, GIF, WebP (max 10MB)</span>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="carousel-upload-error">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          {error}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        onChange={handleInputChange}
        style={{ display: 'none' }}
      />
    </div>
  );
}
