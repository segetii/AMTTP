/**
 * AMTTP Error classes and error codes
 */

export enum AMTTPErrorCode {
  // Network errors
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT = 'TIMEOUT',
  
  // Authentication errors
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  
  // Validation errors
  INVALID_ADDRESS = 'INVALID_ADDRESS',
  INVALID_AMOUNT = 'INVALID_AMOUNT',
  INVALID_PARAMETERS = 'INVALID_PARAMETERS',
  
  // Risk/Compliance errors
  HIGH_RISK_BLOCKED = 'HIGH_RISK_BLOCKED',
  SANCTIONED_ADDRESS = 'SANCTIONED_ADDRESS',
  POLICY_VIOLATION = 'POLICY_VIOLATION',
  KYC_REQUIRED = 'KYC_REQUIRED',
  EDD_REQUIRED = 'EDD_REQUIRED',
  
  // Transaction errors
  INSUFFICIENT_BALANCE = 'INSUFFICIENT_BALANCE',
  TRANSACTION_FAILED = 'TRANSACTION_FAILED',
  ESCROW_REQUIRED = 'ESCROW_REQUIRED',
  
  // Dispute errors
  DISPUTE_NOT_FOUND = 'DISPUTE_NOT_FOUND',
  EVIDENCE_REJECTED = 'EVIDENCE_REJECTED',
  
  // General errors
  NOT_FOUND = 'NOT_FOUND',
  RATE_LIMITED = 'RATE_LIMITED',
  SERVER_ERROR = 'SERVER_ERROR',
  UNKNOWN = 'UNKNOWN',
}

export class AMTTPError extends Error {
  public readonly code: AMTTPErrorCode;
  public readonly statusCode?: number;
  public readonly details?: Record<string, unknown>;

  constructor(
    message: string,
    code: AMTTPErrorCode = AMTTPErrorCode.UNKNOWN,
    statusCode?: number,
    details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'AMTTPError';
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;

    // Maintains proper stack trace for where error was thrown
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, AMTTPError);
    }
  }

  /**
   * Create an error from an API response
   */
  static fromResponse(response: { status: number; data?: { message?: string; code?: string; details?: Record<string, unknown> } }): AMTTPError {
    const message = response.data?.message || 'An error occurred';
    let code = AMTTPErrorCode.UNKNOWN;

    switch (response.status) {
      case 400:
        code = AMTTPErrorCode.INVALID_PARAMETERS;
        break;
      case 401:
        code = AMTTPErrorCode.UNAUTHORIZED;
        break;
      case 403:
        code = response.data?.code === 'SANCTIONED' 
          ? AMTTPErrorCode.SANCTIONED_ADDRESS 
          : AMTTPErrorCode.FORBIDDEN;
        break;
      case 404:
        code = AMTTPErrorCode.NOT_FOUND;
        break;
      case 429:
        code = AMTTPErrorCode.RATE_LIMITED;
        break;
      case 451:
        code = AMTTPErrorCode.POLICY_VIOLATION;
        break;
      case 500:
      case 502:
      case 503:
        code = AMTTPErrorCode.SERVER_ERROR;
        break;
    }

    return new AMTTPError(message, code, response.status, response.data?.details);
  }

  /**
   * Check if error is retryable
   */
  isRetryable(): boolean {
    return [
      AMTTPErrorCode.NETWORK_ERROR,
      AMTTPErrorCode.TIMEOUT,
      AMTTPErrorCode.RATE_LIMITED,
      AMTTPErrorCode.SERVER_ERROR,
    ].includes(this.code);
  }

  /**
   * Check if error requires user action
   */
  requiresUserAction(): boolean {
    return [
      AMTTPErrorCode.KYC_REQUIRED,
      AMTTPErrorCode.EDD_REQUIRED,
      AMTTPErrorCode.INSUFFICIENT_BALANCE,
      AMTTPErrorCode.HIGH_RISK_BLOCKED,
    ].includes(this.code);
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      statusCode: this.statusCode,
      details: this.details,
    };
  }
}
