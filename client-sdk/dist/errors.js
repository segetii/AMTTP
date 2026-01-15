"use strict";
/**
 * AMTTP Error classes and error codes
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AMTTPError = exports.AMTTPErrorCode = void 0;
var AMTTPErrorCode;
(function (AMTTPErrorCode) {
    // Network errors
    AMTTPErrorCode["NETWORK_ERROR"] = "NETWORK_ERROR";
    AMTTPErrorCode["TIMEOUT"] = "TIMEOUT";
    // Authentication errors
    AMTTPErrorCode["UNAUTHORIZED"] = "UNAUTHORIZED";
    AMTTPErrorCode["FORBIDDEN"] = "FORBIDDEN";
    // Validation errors
    AMTTPErrorCode["INVALID_ADDRESS"] = "INVALID_ADDRESS";
    AMTTPErrorCode["INVALID_AMOUNT"] = "INVALID_AMOUNT";
    AMTTPErrorCode["INVALID_PARAMETERS"] = "INVALID_PARAMETERS";
    // Risk/Compliance errors
    AMTTPErrorCode["HIGH_RISK_BLOCKED"] = "HIGH_RISK_BLOCKED";
    AMTTPErrorCode["SANCTIONED_ADDRESS"] = "SANCTIONED_ADDRESS";
    AMTTPErrorCode["POLICY_VIOLATION"] = "POLICY_VIOLATION";
    AMTTPErrorCode["KYC_REQUIRED"] = "KYC_REQUIRED";
    AMTTPErrorCode["EDD_REQUIRED"] = "EDD_REQUIRED";
    // Transaction errors
    AMTTPErrorCode["INSUFFICIENT_BALANCE"] = "INSUFFICIENT_BALANCE";
    AMTTPErrorCode["TRANSACTION_FAILED"] = "TRANSACTION_FAILED";
    AMTTPErrorCode["ESCROW_REQUIRED"] = "ESCROW_REQUIRED";
    // Dispute errors
    AMTTPErrorCode["DISPUTE_NOT_FOUND"] = "DISPUTE_NOT_FOUND";
    AMTTPErrorCode["EVIDENCE_REJECTED"] = "EVIDENCE_REJECTED";
    // General errors
    AMTTPErrorCode["NOT_FOUND"] = "NOT_FOUND";
    AMTTPErrorCode["RATE_LIMITED"] = "RATE_LIMITED";
    AMTTPErrorCode["SERVER_ERROR"] = "SERVER_ERROR";
    AMTTPErrorCode["UNKNOWN"] = "UNKNOWN";
})(AMTTPErrorCode || (exports.AMTTPErrorCode = AMTTPErrorCode = {}));
class AMTTPError extends Error {
    constructor(message, code = AMTTPErrorCode.UNKNOWN, statusCode, details) {
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
    static fromResponse(response) {
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
    isRetryable() {
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
    requiresUserAction() {
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
exports.AMTTPError = AMTTPError;
//# sourceMappingURL=errors.js.map