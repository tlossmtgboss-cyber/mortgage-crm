/**
 * Microsoft Graph Email Service
 * Handles all Microsoft Graph API interactions for email
 */

import { Client } from '@microsoft/microsoft-graph-client';
import { Logger } from 'winston';
import { Email, EmailAddress, Attachment } from '../types';

export class GraphEmailService {
  private graphClient: Client;

  constructor(
    private readonly accessToken: string,
    private readonly logger: Logger
  ) {
    this.graphClient = Client.init({
      authProvider: (done) => {
        done(null, this.accessToken);
      }
    });
  }

  /**
   * Fetch unread emails from inbox
   */
  async getUnreadEmails(limit: number = 50): Promise<Email[]> {
    try {
      const response = await this.graphClient
        .api('/me/mailFolders/inbox/messages')
        .filter('isRead eq false')
        .select('id,subject,body,bodyPreview,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,hasAttachments,importance,isRead,webLink,categories,conversationId')
        .top(limit)
        .orderby('receivedDateTime desc')
        .get();

      return response.value.map((msg: any) => this.mapToEmail(msg));
    } catch (error) {
      this.logger.error('Failed to fetch unread emails', { error });
      throw error;
    }
  }

  /**
   * Fetch a specific email by ID
   */
  async getEmail(emailId: string): Promise<Email> {
    try {
      const msg = await this.graphClient
        .api(`/me/messages/${emailId}`)
        .select('id,subject,body,bodyPreview,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,hasAttachments,importance,isRead,webLink,categories,conversationId')
        .get();

      return this.mapToEmail(msg);
    } catch (error) {
      this.logger.error('Failed to fetch email', { error, emailId });
      throw error;
    }
  }

  /**
   * Fetch email attachments
   */
  async getAttachments(emailId: string): Promise<Attachment[]> {
    try {
      const response = await this.graphClient
        .api(`/me/messages/${emailId}/attachments`)
        .get();

      return response.value.map((att: any) => ({
        id: att.id,
        name: att.name,
        contentType: att.contentType,
        size: att.size,
        isInline: att.isInline || false,
        contentBytes: att.contentBytes
      }));
    } catch (error) {
      this.logger.error('Failed to fetch attachments', { error, emailId });
      throw error;
    }
  }

  /**
   * Send an email
   */
  async sendEmail(
    to: string | string[],
    subject: string,
    body: string,
    isHtml: boolean = true,
    cc?: string[],
    attachments?: Array<{ name: string; content: string; contentType: string }>
  ): Promise<void> {
    const toRecipients = (Array.isArray(to) ? to : [to]).map(email => ({
      emailAddress: { address: email }
    }));

    const ccRecipients = cc?.map(email => ({
      emailAddress: { address: email }
    }));

    const message: any = {
      subject,
      body: {
        contentType: isHtml ? 'HTML' : 'Text',
        content: body
      },
      toRecipients
    };

    if (ccRecipients) {
      message.ccRecipients = ccRecipients;
    }

    if (attachments && attachments.length > 0) {
      message.attachments = attachments.map(att => ({
        '@odata.type': '#microsoft.graph.fileAttachment',
        name: att.name,
        contentBytes: att.content,
        contentType: att.contentType
      }));
    }

    try {
      await this.graphClient
        .api('/me/sendMail')
        .post({ message, saveToSentItems: true });

      this.logger.info('Email sent successfully', { to, subject });
    } catch (error) {
      this.logger.error('Failed to send email', { error, to, subject });
      throw error;
    }
  }

  /**
   * Reply to an email
   */
  async replyToEmail(
    emailId: string,
    body: string,
    isHtml: boolean = true
  ): Promise<void> {
    try {
      await this.graphClient
        .api(`/me/messages/${emailId}/reply`)
        .post({
          message: {
            body: {
              contentType: isHtml ? 'HTML' : 'Text',
              content: body
            }
          }
        });

      this.logger.info('Reply sent successfully', { emailId });
    } catch (error) {
      this.logger.error('Failed to reply to email', { error, emailId });
      throw error;
    }
  }

  /**
   * Mark email as read
   */
  async markAsRead(emailId: string): Promise<void> {
    try {
      await this.graphClient
        .api(`/me/messages/${emailId}`)
        .update({ isRead: true });
    } catch (error) {
      this.logger.error('Failed to mark email as read', { error, emailId });
      throw error;
    }
  }

  /**
   * Move email to folder
   */
  async moveToFolder(emailId: string, folderId: string): Promise<void> {
    try {
      await this.graphClient
        .api(`/me/messages/${emailId}/move`)
        .post({ destinationId: folderId });
    } catch (error) {
      this.logger.error('Failed to move email', { error, emailId, folderId });
      throw error;
    }
  }

  /**
   * Create or get a folder by name
   */
  async getOrCreateFolder(folderName: string): Promise<string> {
    try {
      // Try to find existing folder
      const response = await this.graphClient
        .api('/me/mailFolders')
        .filter(`displayName eq '${folderName}'`)
        .get();

      if (response.value.length > 0) {
        return response.value[0].id;
      }

      // Create new folder
      const newFolder = await this.graphClient
        .api('/me/mailFolders')
        .post({ displayName: folderName });

      return newFolder.id;
    } catch (error) {
      this.logger.error('Failed to get/create folder', { error, folderName });
      throw error;
    }
  }

  /**
   * Create webhook subscription for new emails
   */
  async createSubscription(
    webhookUrl: string,
    expirationMinutes: number = 4230 // ~3 days max for mail
  ): Promise<string> {
    const expirationDateTime = new Date();
    expirationDateTime.setMinutes(expirationDateTime.getMinutes() + expirationMinutes);

    try {
      const subscription = await this.graphClient
        .api('/subscriptions')
        .post({
          changeType: 'created',
          notificationUrl: webhookUrl,
          resource: '/me/mailFolders/inbox/messages',
          expirationDateTime: expirationDateTime.toISOString(),
          clientState: process.env.WEBHOOK_SECRET || 'perennia-email-orchestrator'
        });

      this.logger.info('Webhook subscription created', {
        subscriptionId: subscription.id,
        expiresAt: subscription.expirationDateTime
      });

      return subscription.id;
    } catch (error) {
      this.logger.error('Failed to create subscription', { error });
      throw error;
    }
  }

  /**
   * Renew webhook subscription
   */
  async renewSubscription(subscriptionId: string): Promise<void> {
    const expirationDateTime = new Date();
    expirationDateTime.setMinutes(expirationDateTime.getMinutes() + 4230);

    try {
      await this.graphClient
        .api(`/subscriptions/${subscriptionId}`)
        .update({
          expirationDateTime: expirationDateTime.toISOString()
        });

      this.logger.info('Subscription renewed', { subscriptionId });
    } catch (error) {
      this.logger.error('Failed to renew subscription', { error, subscriptionId });
      throw error;
    }
  }

  /**
   * Map Graph API response to Email type
   */
  private mapToEmail(msg: any): Email {
    return {
      id: msg.id,
      messageId: msg.internetMessageId || msg.id,
      conversationId: msg.conversationId,
      subject: msg.subject || '(No Subject)',
      body: msg.body?.content || '',
      bodyPreview: msg.bodyPreview || '',
      from: this.mapEmailAddress(msg.from?.emailAddress),
      to: (msg.toRecipients || []).map((r: any) => this.mapEmailAddress(r.emailAddress)),
      cc: (msg.ccRecipients || []).map((r: any) => this.mapEmailAddress(r.emailAddress)),
      receivedDateTime: new Date(msg.receivedDateTime),
      sentDateTime: msg.sentDateTime ? new Date(msg.sentDateTime) : undefined,
      hasAttachments: msg.hasAttachments || false,
      importance: msg.importance || 'normal',
      isRead: msg.isRead || false,
      webLink: msg.webLink,
      categories: msg.categories || []
    };
  }

  /**
   * Map email address from Graph API format
   */
  private mapEmailAddress(addr: any): EmailAddress {
    return {
      name: addr?.name,
      address: addr?.address || ''
    };
  }
}
