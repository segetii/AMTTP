/**
 * AMTTP Error classes and error codes
 */
export declare enum AMTTPErrorCode {
    NETWORK_ERROR = "NETWORK_ERROR",
    TIMEOUT = "TIMEOUT",
    UNAUTHORIZED = "UNAUTHORIZED",
    FORBIDDEN = "FORBIDDEN",
    INVALID_ADDRESS = "INVALID_ADDRESS",
    INVALID_AMOUNT = "INVALID_AMOUNT",
    INVALID_PARAMETERS = "INVALID_PARAMETERS",
    HIGH_RISK_BLOCKED = "HIGH_RISK_BLOCKED",
    SANCTIONED_ADDRESS = "SANCTIONED_ADDRESS",
    POLICY_VIOLATION = "POLICY_VIOLATION",
    KYC_REQUIRED = "KYC_REQUIRED",
    EDD_REQUIRED = "EDD_REQUIRED",
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE",
    TRANSACTION_FAILED = "TRANSACTION_FAILED",
    ESCROW_REQUIRED = "ESCROW_REQUIRED",
    DISPUTE_NOT_FOUND = "DISPUTE_NOT_FOUND",
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED",
    NOT_FOUND = "NOT_FOUND",
    RATE_LIMITED = "RATE_LIMITED",
    SERVER_ERROR = "SERVER_ERROR",
    UNKNOWN = "UNKNOWN"
}
export declare class AMTTPError extends Error {
    readonly code: AMTTPErrorCode;
    readonly statusCode?: number;
    readonly details?: Record<string, unknown>;
    constructor(message: string, code?: AMTTPErrorCode, statusCode?: number, details?: Record<string, unknown>);
    /**
     * Create an error from an API response
     */
    static fromResponse(response: {
        status: number;
        data?: {
            message?: string;
            code?: string;
            details?: Record<string, unknown>;
        };
    }): AMTTPError;
    /**
     * Check if error is retryable
     */
    isRetryable(): boolean;
    /**
     * Check if error requires user action
     */
    requiresUserAction(): boolean;
    toJSON(): {
        name: string;
        message: string;
        code: AMTTPErrorCode;
        statusCode: number | undefined;
        details: Record<string, unknown> | undefined;
    };
}
//# sourceMappingURL=errors.d.ts.map