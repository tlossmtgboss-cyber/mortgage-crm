/**
 * QuestionRenderer - Renders individual questions with appropriate input type
 * Handles transitions and navigation between questions
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { QuestionTypes } from '../config/purchaseQuestions';
import { toast } from '../../../utils/toast';
import {
  ChoiceInput,
  TextInput,
  EmailInput,
  CurrencyInput,
  SSNInput,
  DateInput,
  PhoneInput,
  PercentageInput,
  AddressInput,
  EmployerInput,
  BooleanInput,
  StateSelect,
  RealtorLookupInput,
  CalendarSchedulerInput,
  DurationInput,
  DownpaymentInput,
  FileUploadInput,
} from './inputs';
import './QuestionRenderer.css';

const QuestionRenderer = ({
  question,
  value,
  onChange,
  onNext,
  onBack,
  isFirst = false,
  isLast = false,
  error,
  currentIndex,
  totalQuestions,
  autoAdvance = true,
}) => {
  const [isAnimating, setIsAnimating] = useState(false);
  const [animationDirection, setAnimationDirection] = useState('forward');
  const inputRef = useRef(null);

  // Focus input on mount
  useEffect(() => {
    const timer = setTimeout(() => {
      if (inputRef.current?.focus) {
        inputRef.current.focus();
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [question?.id]);

  // Handle value change with optional auto-advance
  const handleChange = useCallback((newValue) => {
    onChange(newValue);

    // Auto-advance for single-choice and boolean types
    if (autoAdvance && !isLast) {
      const shouldAdvance =
        (question.type === QuestionTypes.SINGLE_CHOICE && newValue) ||
        (question.type === QuestionTypes.BOOLEAN && newValue !== null && newValue !== undefined);

      if (shouldAdvance) {
        setAnimationDirection('forward');
        setIsAnimating(true);
        setTimeout(() => {
          onNext();
          setIsAnimating(false);
        }, 300);
      }
    }
  }, [onChange, onNext, isLast, question?.type, autoAdvance]);

  // Handle next button click
  const handleNext = () => {
    if (isLast) {
      onNext(); // This will trigger stage completion
      return;
    }

    setAnimationDirection('forward');
    setIsAnimating(true);
    setTimeout(() => {
      onNext();
      setIsAnimating(false);
    }, 300);
  };

  // Handle back button click
  const handleBack = () => {
    if (isFirst) {
      onBack(); // This will trigger stage navigation
      return;
    }

    setAnimationDirection('backward');
    setIsAnimating(true);
    setTimeout(() => {
      onBack();
      setIsAnimating(false);
    }, 300);
  };

  // Handle keyboard navigation
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      // Check if current input allows enter to advance
      const enterAdvanceTypes = [
        QuestionTypes.TEXT,
        QuestionTypes.EMAIL,
        QuestionTypes.PHONE,
        QuestionTypes.CURRENCY,
        QuestionTypes.PERCENTAGE,
        QuestionTypes.NUMBER,
        QuestionTypes.DATE,
        QuestionTypes.SSN,
      ];

      if (enterAdvanceTypes.includes(question?.type) && value) {
        e.preventDefault();
        handleNext();
      }
    }
  };

  // Render the appropriate input component
  const renderInput = () => {
    if (!question) return null;

    const commonProps = {
      value,
      onChange: handleChange,
      error,
      disabled: isAnimating,
      required: question.required,
      helpText: question.helpText,
      placeholder: question.placeholder,
    };

    switch (question.type) {
      case QuestionTypes.SINGLE_CHOICE:
        return (
          <ChoiceInput
            {...commonProps}
            options={question.options || []}
            multiple={false}
            columns={question.columns || 2}
          />
        );

      case QuestionTypes.MULTI_CHOICE:
        return (
          <ChoiceInput
            {...commonProps}
            options={question.options || []}
            multiple={true}
            columns={question.columns || 2}
          />
        );

      case QuestionTypes.BOOLEAN:
        return (
          <BooleanInput
            {...commonProps}
            yesLabel={question.yesLabel || 'Yes'}
            noLabel={question.noLabel || 'No'}
          />
        );

      case QuestionTypes.TEXT:
        return (
          <TextInput
            ref={inputRef}
            {...commonProps}
            onKeyDown={handleKeyDown}
            maxLength={question.maxLength}
          />
        );

      case QuestionTypes.EMAIL:
        return (
          <EmailInput
            ref={inputRef}
            {...commonProps}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.PHONE:
        return (
          <PhoneInput
            ref={inputRef}
            {...commonProps}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.CURRENCY:
        return (
          <CurrencyInput
            ref={inputRef}
            {...commonProps}
            min={question.min}
            max={question.max}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.PERCENTAGE:
        return (
          <PercentageInput
            ref={inputRef}
            {...commonProps}
            min={question.min ?? 0}
            max={question.max ?? 100}
            decimals={question.decimals ?? 2}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.NUMBER:
        return (
          <TextInput
            ref={inputRef}
            {...commonProps}
            type="number"
            inputMode="numeric"
            min={question.min}
            max={question.max}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.DATE:
        return (
          <DateInput
            ref={inputRef}
            {...commonProps}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.SSN:
        return (
          <SSNInput
            ref={inputRef}
            {...commonProps}
            onKeyDown={handleKeyDown}
          />
        );

      case QuestionTypes.ADDRESS:
        return (
          <AddressInput
            {...commonProps}
          />
        );

      case QuestionTypes.EMPLOYER:
        return (
          <EmployerInput
            {...commonProps}
          />
        );

      case QuestionTypes.STATE_SELECT:
        return (
          <StateSelect
            {...commonProps}
          />
        );

      case QuestionTypes.INFO:
        // Display-only informational text (no input)
        return (
          <div className="question-info-display" style={question.infoStyle || {}}>
            <p className="info-text">{question.infoText || question.helpText}</p>
          </div>
        );

      case QuestionTypes.ECONSENT:
        // Electronic consent with full verbiage and agree/disagree buttons
        return (
          <div className="econsent-container">
            <div className="econsent-content">
              <p className="econsent-intro">{question.eConsentContent?.intro}</p>
              <div className="econsent-scrollbox">
                {question.eConsentContent?.sections?.map((section, idx) => (
                  <div key={idx} className="econsent-section-item">
                    {section.title && <h4>{section.title}</h4>}
                    {section.content.split('\n\n').map((para, pIdx) => (
                      <p key={pIdx}>{para}</p>
                    ))}
                  </div>
                ))}
              </div>
              <div className="econsent-actions">
                <button
                  type="button"
                  className={`econsent-btn agree ${value === true ? 'selected' : ''}`}
                  onClick={() => handleChange(true)}
                >
                  <span className="btn-icon">✓</span>
                  I Agree
                </button>
                <button
                  type="button"
                  className="econsent-btn disagree"
                  onClick={() => {
                    handleChange(false);
                    toast.success('You have chosen not to consent to electronic documents. Paper documents will be mailed to you. You can still proceed with your application.');
                  }}
                >
                  I Do Not Agree
                </button>
              </div>
            </div>
          </div>
        );

      case QuestionTypes.CREDIT_AUTH:
        // Credit authorization with verbiage and authorize/decline buttons
        return (
          <div className="credit-auth-container">
            <div className="credit-auth-content">
              <p className="credit-auth-intro">{question.creditAuthContent?.intro}</p>
              <div className="credit-auth-box">
                <p>{question.creditAuthContent?.authorization}</p>
              </div>
              <div className="credit-auth-actions">
                <button
                  type="button"
                  className={`credit-auth-btn authorize ${value === true ? 'selected' : ''}`}
                  onClick={() => handleChange(true)}
                >
                  <span className="btn-icon">✓</span>
                  I Authorize
                </button>
                <button
                  type="button"
                  className="credit-auth-btn decline"
                  onClick={() => {
                    handleChange(false);
                    toast.error('Credit authorization is required to process your mortgage application. Without it, we cannot verify your creditworthiness.');
                  }}
                >
                  I Do Not Authorize
                </button>
              </div>
            </div>
          </div>
        );

      case QuestionTypes.REALTOR_LOOKUP:
        // Realtor CRM lookup with auto-populate
        return (
          <RealtorLookupInput
            {...commonProps}
            onAgentSelect={(agent) => {
              // When agent is selected from CRM, set flag to skip email/phone questions
              if (agent.fromCrm) {
                // This will be handled by the parent context
              }
            }}
          />
        );

      case QuestionTypes.CALENDAR_SCHEDULER:
        // Smart calendar appointment scheduling
        return (
          <CalendarSchedulerInput
            {...commonProps}
            appointmentType={question.appointmentType || 'consultation'}
            duration={question.duration || 30}
          />
        );

      case QuestionTypes.DURATION:
        // Combined years and months input
        return (
          <DurationInput
            {...commonProps}
          />
        );

      case QuestionTypes.DOWNPAYMENT:
        // Combined amount or percentage input
        return (
          <DownpaymentInput
            {...commonProps}
          />
        );

      case QuestionTypes.FILE_UPLOAD:
        // File upload with document parsing
        return (
          <FileUploadInput
            {...commonProps}
            acceptedTypes={question.acceptedTypes || '.pdf,.jpg,.jpeg,.png'}
            documentType={question.documentType || 'document'}
          />
        );

      default:
        // For display-only text or unknown types
        return (
          <div className="question-info-text">
            {question.helpText || question.description}
          </div>
        );
    }
  };

  // Check if can proceed (has value for required fields)
  const canProceed = () => {
    if (!question?.required) return true;
    if (value === null || value === undefined || value === '') return false;
    if (Array.isArray(value) && value.length === 0) return false;
    return true;
  };

  if (!question) return null;

  return (
    <div
      className={`question-renderer ${isAnimating ? `animating-${animationDirection}` : ''}`}
      role="form"
      aria-label={question.question}
    >
      {/* Question progress */}
      <div className="question-progress">
        <span className="question-count">
          Question {currentIndex + 1} of {totalQuestions}
        </span>
      </div>

      {/* Question text */}
      <div className="question-header">
        <h2 className="question-text">
          {question.question}
          {question.required && <span className="required-indicator">*</span>}
        </h2>
        {question.subQuestion && (
          <p className="question-subtext">{question.subQuestion}</p>
        )}
      </div>

      {/* Input area */}
      <div className="question-input">
        {renderInput()}
      </div>

      {/* Navigation buttons */}
      <div className="question-navigation">
        <button
          type="button"
          className="nav-btn nav-btn-back"
          onClick={handleBack}
          disabled={isAnimating}
        >
          ← Back
        </button>

        <button
          type="button"
          className={`nav-btn nav-btn-next ${!canProceed() ? 'disabled' : ''}`}
          onClick={handleNext}
          disabled={isAnimating || !canProceed()}
        >
          {isLast ? 'Continue to Next Section' : 'Next →'}
        </button>
      </div>

      {/* Keyboard hint */}
      <div className="keyboard-hint">
        Press <kbd>Enter</kbd> to continue
      </div>
    </div>
  );
};

export default QuestionRenderer;
