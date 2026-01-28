/**
 * Alert Types
 * 
 * Sprint 10: Real-Time Alerts & Notifications
 * 
 * Ground Truth Reference:
 * - Immediate notification of critical events
 * - Configurable alert rules and thresholds
 * - Multi-channel delivery (UI, email, webhook)
 */

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT PRIORITY
// ═══════════════════════════════════════════════════════════════════════════════

export enum AlertPriority {
  LOW = 'LOW',           // Informational
  MEDIUM = 'MEDIUM',     // Attention needed
  HIGH = 'HIGH',         // Urgent action required
  CRITICAL = 'CRITICAL', // Immediate action required
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT CATEGORY
// ═══════════════════════════════════════════════════════════════════════════════

export enum AlertCategory {
  // Security
  SECURITY = 'SECURITY',
  AUTHENTICATION = 'AUTHENTICATION',
  AUTHORIZATION = 'AUTHORIZATION',
  
  // Compliance
  COMPLIANCE = 'COMPLIANCE',
  AML = 'AML',
  SANCTIONS = 'SANCTIONS',
  
  // Operations
  TRANSFER = 'TRANSFER',
  ESCROW = 'ESCROW',
  DISPUTE = 'DISPUTE',
  
  // System
  SYSTEM = 'SYSTEM',
  INFRASTRUCTURE = 'INFRASTRUCTURE',
  PERFORMANCE = 'PERFORMANCE',
  
  // Governance
  GOVERNANCE = 'GOVERNANCE',
  POLICY = 'POLICY',
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT STATUS
// ═══════════════════════════════════════════════════════════════════════════════

export enum AlertStatus {
  NEW = 'NEW',
  ACKNOWLEDGED = 'ACKNOWLEDGED',
  IN_PROGRESS = 'IN_PROGRESS',
  RESOLVED = 'RESOLVED',
  DISMISSED = 'DISMISSED',
  ESCALATED = 'ESCALATED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT
// ═══════════════════════════════════════════════════════════════════════════════

export interface Alert {
  id: string;
  
  // Classification
  priority: AlertPriority;
  category: AlertCategory;
  status: AlertStatus;
  
  // Content
  title: string;
  message: string;
  details?: string;
  
  // Context
  source: AlertSource;
  resourceType?: string;
  resourceId?: string;
  relatedAlertIds?: string[];
  
  // Metadata
  metadata: Record<string, unknown>;
  tags: string[];
  
  // Timestamps
  createdAt: number;
  acknowledgedAt?: number;
  resolvedAt?: number;
  expiresAt?: number;
  
  // Actors
  acknowledgedBy?: string;
  resolvedBy?: string;
  assignedTo?: string;
  
  // Actions
  actions: AlertAction[];
  resolution?: AlertResolution;
  
  // Delivery
  deliveryChannels: DeliveryChannel[];
  deliveryStatus: DeliveryStatus[];
}

export interface AlertSource {
  type: 'SYSTEM' | 'RULE' | 'ORACLE' | 'USER' | 'CONTRACT';
  id: string;
  name: string;
}

export interface AlertAction {
  id: string;
  label: string;
  type: 'primary' | 'secondary' | 'danger';
  actionType: ActionType;
  actionData?: Record<string, unknown>;
}

export enum ActionType {
  ACKNOWLEDGE = 'ACKNOWLEDGE',
  DISMISS = 'DISMISS',
  ESCALATE = 'ESCALATE',
  ASSIGN = 'ASSIGN',
  VIEW_DETAILS = 'VIEW_DETAILS',
  NAVIGATE = 'NAVIGATE',
  EXECUTE_ACTION = 'EXECUTE_ACTION',
}

export interface AlertResolution {
  type: 'RESOLVED' | 'DISMISSED' | 'AUTO_RESOLVED' | 'EXPIRED';
  reason?: string;
  notes?: string;
  timestamp: number;
  resolvedBy: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DELIVERY
// ═══════════════════════════════════════════════════════════════════════════════

export enum DeliveryChannel {
  UI = 'UI',
  EMAIL = 'EMAIL',
  SMS = 'SMS',
  WEBHOOK = 'WEBHOOK',
  SLACK = 'SLACK',
  TELEGRAM = 'TELEGRAM',
  PUSH = 'PUSH',
}

export interface DeliveryStatus {
  channel: DeliveryChannel;
  status: 'PENDING' | 'SENT' | 'DELIVERED' | 'FAILED';
  sentAt?: number;
  deliveredAt?: number;
  errorMessage?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT RULE
// ═══════════════════════════════════════════════════════════════════════════════

export interface AlertRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  
  // Trigger conditions
  conditions: AlertCondition[];
  conditionLogic: 'AND' | 'OR';
  
  // Alert configuration
  priority: AlertPriority;
  category: AlertCategory;
  titleTemplate: string;
  messageTemplate: string;
  
  // Delivery configuration
  channels: DeliveryChannel[];
  recipients: AlertRecipient[];
  
  // Rate limiting
  cooldownMinutes: number;
  maxAlertsPerHour?: number;
  
  // Schedule
  schedule?: AlertSchedule;
  
  // Metadata
  tags: string[];
  createdAt: number;
  updatedAt: number;
  createdBy: string;
}

export interface AlertCondition {
  field: string;
  operator: ConditionOperator;
  value: string | number | boolean;
  valueType: 'string' | 'number' | 'boolean' | 'array';
}

export enum ConditionOperator {
  EQUALS = 'EQUALS',
  NOT_EQUALS = 'NOT_EQUALS',
  GREATER_THAN = 'GREATER_THAN',
  LESS_THAN = 'LESS_THAN',
  GREATER_THAN_OR_EQUAL = 'GREATER_THAN_OR_EQUAL',
  LESS_THAN_OR_EQUAL = 'LESS_THAN_OR_EQUAL',
  CONTAINS = 'CONTAINS',
  NOT_CONTAINS = 'NOT_CONTAINS',
  IN = 'IN',
  NOT_IN = 'NOT_IN',
  MATCHES = 'MATCHES', // regex
  EXISTS = 'EXISTS',
  NOT_EXISTS = 'NOT_EXISTS',
}

export interface AlertRecipient {
  type: 'USER' | 'ROLE' | 'GROUP' | 'EMAIL' | 'WEBHOOK';
  value: string;
  channels?: DeliveryChannel[];
}

export interface AlertSchedule {
  timezone: string;
  activeDays: number[]; // 0-6, Sunday = 0
  activeHoursStart: number; // 0-23
  activeHoursEnd: number; // 0-23
  excludeDates?: string[]; // ISO date strings
}

// ═══════════════════════════════════════════════════════════════════════════════
// NOTIFICATION PREFERENCES
// ═══════════════════════════════════════════════════════════════════════════════

export interface NotificationPreferences {
  userId: string;
  
  // Global settings
  enabled: boolean;
  doNotDisturb: boolean;
  doNotDisturbUntil?: number;
  
  // Channel preferences
  channels: {
    [K in DeliveryChannel]?: {
      enabled: boolean;
      minPriority: AlertPriority;
    };
  };
  
  // Category preferences
  categories: {
    [K in AlertCategory]?: {
      enabled: boolean;
      channels?: DeliveryChannel[];
    };
  };
  
  // Sound & display
  soundEnabled: boolean;
  desktopNotifications: boolean;
  showPreview: boolean;
  
  // Digest settings
  digestEnabled: boolean;
  digestFrequency: 'HOURLY' | 'DAILY' | 'WEEKLY';
  digestTime?: string; // HH:mm format
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT STATISTICS
// ═══════════════════════════════════════════════════════════════════════════════

export interface AlertStats {
  timeRange: {
    start: number;
    end: number;
  };
  
  // Counts
  total: number;
  byPriority: Record<AlertPriority, number>;
  byCategory: Record<AlertCategory, number>;
  byStatus: Record<AlertStatus, number>;
  
  // Response metrics
  avgAcknowledgeTime: number; // seconds
  avgResolutionTime: number; // seconds
  acknowledgeRate: number; // percentage
  resolutionRate: number; // percentage
  
  // Trends
  alertsOverTime: Array<{ timestamp: number; count: number }>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getPriorityColor(priority: AlertPriority): string {
  const colors: Record<AlertPriority, string> = {
    [AlertPriority.LOW]: 'blue',
    [AlertPriority.MEDIUM]: 'yellow',
    [AlertPriority.HIGH]: 'orange',
    [AlertPriority.CRITICAL]: 'red',
  };
  return colors[priority];
}

export function getCategoryIcon(category: AlertCategory): string {
  const icons: Record<AlertCategory, string> = {
    [AlertCategory.SECURITY]: '🔐',
    [AlertCategory.AUTHENTICATION]: '🔑',
    [AlertCategory.AUTHORIZATION]: '🛡️',
    [AlertCategory.COMPLIANCE]: '⚖️',
    [AlertCategory.AML]: '🔍',
    [AlertCategory.SANCTIONS]: '🚫',
    [AlertCategory.TRANSFER]: '💸',
    [AlertCategory.ESCROW]: '🔒',
    [AlertCategory.DISPUTE]: '⚔️',
    [AlertCategory.SYSTEM]: '⚙️',
    [AlertCategory.INFRASTRUCTURE]: '🖥️',
    [AlertCategory.PERFORMANCE]: '📈',
    [AlertCategory.GOVERNANCE]: '🏛️',
    [AlertCategory.POLICY]: '📋',
  };
  return icons[category];
}

export function getStatusColor(status: AlertStatus): string {
  const colors: Record<AlertStatus, string> = {
    [AlertStatus.NEW]: 'cyan',
    [AlertStatus.ACKNOWLEDGED]: 'yellow',
    [AlertStatus.IN_PROGRESS]: 'blue',
    [AlertStatus.RESOLVED]: 'green',
    [AlertStatus.DISMISSED]: 'gray',
    [AlertStatus.ESCALATED]: 'red',
  };
  return colors[status];
}

export function formatAlertTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return new Date(timestamp).toLocaleDateString();
}
